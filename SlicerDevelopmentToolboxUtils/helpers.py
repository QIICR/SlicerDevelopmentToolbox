import ast
import logging
import os
import sys
import urllib
from urllib import FancyURLopener

import DICOMLib
import qt
import slicer
import vtk
from DICOMLib import DICOMProcess
from events import SlicerDevelopmentToolboxEvents
from mixins import ModuleLogicMixin, ParameterNodeObservationMixin


class SampleDataDownloader(FancyURLopener, ParameterNodeObservationMixin):

  EVENTS = {'status_changed': SlicerDevelopmentToolboxEvents.StatusChangedEvent,
            'download_canceled': SlicerDevelopmentToolboxEvents.DownloadCanceledEvent, # TODO: Implement cancel
            'download_finished': SlicerDevelopmentToolboxEvents.DownloadFinishedEvent,
            'download_failed': SlicerDevelopmentToolboxEvents.DownloadFailedEvent}

  def __init__(self, enableLogging=False):
    super(SampleDataDownloader, self).__init__()
    self.loggingEnabled = enableLogging
    self.isDownloading = False
    self.resetAndInitialize()

  def __del__(self):
    super(SampleDataDownloader, self).__del__()

  def resetAndInitialize(self):
    self._cancelDownload=False
    self.wasCanceled = False
    if self.isDownloading:
      self.cancelDownload()
    self.removeEventObservers()
    if self.loggingEnabled:
      self._addOwnObservers()

  def _addOwnObservers(self):
    for event in self.EVENTS.values():
      self.addEventObserver(event, self.logMessage)

  @vtk.calldata_type(vtk.VTK_STRING)
  def logMessage(self, caller, event, callData):
    message, _ = ast.literal_eval(callData)
    logging.debug(message)

  def downloadFileIntoCache(self, uri, name):
    return self.downloadFile(uri, slicer.mrmlScene.GetCacheManager().GetRemoteCacheDirectory(), name)

  def downloadFile(self, uri, destFolderPath, name):
    if self.isDownloading:
      self.cancelDownload()
    self._cancelDownload = False
    self.wasCanceled = False
    filePath = os.path.join(destFolderPath, name)
    if not os.path.exists(filePath) or os.stat(filePath).st_size == 0:
      self.downloadPercent = 0
      self.invokeEvent(self.EVENTS['status_changed'], ['Requesting download %s from %s...' % (name, uri),
                                                       self.downloadPercent].__str__())
      try:
        self.isDownloading = True
        self.retrieve(uri, filePath, self.reportHook)
        self.invokeEvent(self.EVENTS['status_changed'], ['Download finished', self.downloadPercent].__str__())
        # self.invokeEvent(self.EVENTS['download_finished'])
      except IOError as e:
        self.invokeEvent(self.EVENTS['download_failed'], ['Download failed: %s' % e, self.downloadPercent].__str__())
    else:
      self.invokeEvent(self.EVENTS['status_changed'], ['File already exists in cache - reusing it.', 100].__str__())
    return filePath

  def cancelDownload(self):
    self._cancelDownload=True

  def humanFormatSize(self, size):
    """ from http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size"""
    for x in ['bytes', 'KB', 'MB', 'GB']:
      if -1024.0 < size < 1024.0:
        return "%3.1f %s" % (size, x)
      size /= 1024.0
    return "%3.1f %s" % (size, 'TB')

  def reportHook(self, blocksSoFar, blockSize, totalSize):
    percent = min(int((100. * blocksSoFar * blockSize) / totalSize), 100)
    humanSizeSoFar = self.humanFormatSize(min(blocksSoFar * blockSize, totalSize))
    humanSizeTotal = self.humanFormatSize(totalSize)
    self.downloadPercent = percent
    self.invokeEvent(self.EVENTS['status_changed'],
                     ['Downloaded %s (%d%% of %s)...' % (humanSizeSoFar, percent, humanSizeTotal),
                      self.downloadPercent].__str__())

  def retrieve(self, url, filename=None, reporthook=None, data=None):
    # overridden method from urllib.URLopener
    self._cancelDownload=False
    url = urllib.unwrap(urllib.toBytes(url))
    if self.tempcache and url in self.tempcache:
      return self.tempcache[url]
    type, url1 = urllib.splittype(url)
    if filename is None and (not type or type == 'file'):
      try:
        fp = self.open_local_file(url1)
        hdrs = fp.info()
        fp.close()
        return urllib.url2pathname(urllib.splithost(url1)[1]), hdrs
      except IOError:
        pass
    fp = self.open(url, data)
    try:
      headers = fp.info()
      if filename:
        tfp = open(filename, 'wb')
      else:
        import tempfile
        garbage, path = urllib.splittype(url)
        garbage, path = urllib.splithost(path or "")
        path, garbage = urllib.splitquery(path or "")
        path, garbage = urllib.splitattr(path or "")
        suffix = os.path.splitext(path)[1]
        (fd, filename) = tempfile.mkstemp(suffix)
        self.__tempfiles.append(filename)
        tfp = os.fdopen(fd, 'wb')
      try:
        result = filename, headers
        if self.tempcache is not None:
          self.tempcache[url] = result
        bs = 1024 * 8
        size = -1
        read = 0
        blocknum = 0
        if "content-length" in headers:
          size = int(headers["Content-Length"])
        if reporthook:
          reporthook(blocknum, bs, size)
        while not self._cancelDownload:
          block = fp.read(bs)
          if block == "":
            break
          read += len(block)
          tfp.write(block)
          blocknum += 1
          if reporthook:
            reporthook(blocknum, bs, size)
      finally:
        tfp.close()
    finally:
      fp.close()

    # raise exception if actual size does not match content-length header
    if size >= 0 and read < size:
      raise urllib.ContentTooShortError("retrieval incomplete: got only %i out "
                                 "of %i bytes" % (read, size), result)

    if self._cancelDownload and os.path.exists(filename):
      os.remove(filename)
      self.wasCanceled = True
    return result


class DirectoryWatcher(ModuleLogicMixin):

  StartedWatchingEvent = SlicerDevelopmentToolboxEvents.DICOMReceiverStartedEvent
  StoppedWatchingEvent = SlicerDevelopmentToolboxEvents.DICOMReceiverStoppedEvent
  IncomingFileCountChangedEvent = SlicerDevelopmentToolboxEvents.IncomingFileCountChangedEvent

  SUPPORTED_EVENTS = [StartedWatchingEvent, StoppedWatchingEvent, IncomingFileCountChangedEvent]

  def __init__(self, directory):
    self.observedDirectory = directory
    self.setupTimers()
    self.reset()

  def __del__(self):
    self.stop()
    super(DirectoryWatcher, self).__del__()

  def reset(self):
    self.startingFileList = []
    self.currentFileList = []
    self.currentStatus = ""
    self._running = False

  def isRunning(self):
    return self._running

  def setupTimers(self):
    self.watchTimer = self.createTimer(interval=1000, slot=self._startWatching, singleShot=True)

  def start(self):
    self.stop()
    self.startingFileList = self.getFileList(self.observedDirectory)
    self.lastFileCount = len(self.startingFileList)
    self._running = True
    self._startWatching()
    self.invokeEvent(self.StartedWatchingEvent)

  def stop(self):
    if self._running:
      self.watchTimer.stop()
      self.reset()
      self.invokeEvent(self.StoppedWatchingEvent)

  def _startWatching(self):
    if not self.isRunning:
      return
    self.currentFileList = self.getFileList(self.observedDirectory)
    currentFileListCount = len(self.currentFileList)
    if self.lastFileCount != currentFileListCount:
      self._onFileCountChanged(currentFileListCount)
    else:
      self.watchTimer.start()

  def _onFileCountChanged(self, currentFileListCount):
    self.lastFileCount = currentFileListCount
    receivedFileCount = abs(len(self.startingFileList) - currentFileListCount)
    self.invokeEvent(self.IncomingFileCountChangedEvent, receivedFileCount)
    self.watchTimer.start()


class TimeoutDirectoryWatcher(DirectoryWatcher):

  IncomingDataReceiveFinishedEvent = SlicerDevelopmentToolboxEvents.IncomingDataReceiveFinishedEvent

  SUPPORTED_EVENTS = DirectoryWatcher.SUPPORTED_EVENTS + [IncomingDataReceiveFinishedEvent]

  def __init__(self, directory, timeout=5000):
    self.receiveFinishedTimeout = timeout
    super(TimeoutDirectoryWatcher, self).__init__(directory)

  def setupTimers(self):
    super(TimeoutDirectoryWatcher, self).setupTimers()
    self.dataReceivedTimer = self.createTimer(interval=5000, slot=self._checkIfStillSameFileCount, singleShot=True)

  def stop(self):
    if self._running:
      self.dataReceivedTimer.stop()
    super(TimeoutDirectoryWatcher, self).stop()

  def _startWatching(self):
    if not self.isRunning:
      return
    self.currentFileList = self.getFileList(self.observedDirectory)
    currentFileListCount = len(self.currentFileList)
    if self.lastFileCount != currentFileListCount:
      self._onFileCountChanged(currentFileListCount)
    elif currentFileListCount != len(self.startingFileList):
      self.lastFileCount = currentFileListCount
      self.dataReceivedTimer.start()
    else:
      self.watchTimer.start()

  def _checkIfStillSameFileCount(self):
    self.currentFileList = self.getFileList(self.observedDirectory)
    if self.lastFileCount == len(self.currentFileList):
      newFileList = list(set(self.currentFileList) - set(self.startingFileList))
      self.startingFileList = self.currentFileList
      self.lastFileCount = len(self.startingFileList)
      if len(newFileList):
        self.invokeEvent(self.IncomingDataReceiveFinishedEvent, newFileList.__str__())
    self.watchTimer.start()


class SmartDICOMReceiver(ModuleLogicMixin):

  NAME = "SmartDICOMReceiver"
  STATUS_RECEIVING = "{}: Receiving DICOM data".format(NAME)

  StatusChangedEvent = SlicerDevelopmentToolboxEvents.StatusChangedEvent
  DICOMReceiverStartedEvent = SlicerDevelopmentToolboxEvents.DICOMReceiverStartedEvent
  DICOMReceiverStoppedEvent = SlicerDevelopmentToolboxEvents.DICOMReceiverStoppedEvent
  IncomingDataReceiveFinishedEvent = TimeoutDirectoryWatcher.IncomingDataReceiveFinishedEvent
  IncomingFileCountChangedEvent = TimeoutDirectoryWatcher.IncomingFileCountChangedEvent

  SUPPORTED_EVENTS = [DICOMReceiverStartedEvent, DICOMReceiverStoppedEvent, StatusChangedEvent,
                      IncomingDataReceiveFinishedEvent, IncomingFileCountChangedEvent]

  def __init__(self, incomingDataDirectory):
    self.incomingDataDirectory = incomingDataDirectory
    self.directoryWatcher = TimeoutDirectoryWatcher(incomingDataDirectory)
    self.connectEvents()
    self.storeSCPProcess = None
    self.reset()
    slicer.app.connect('aboutToQuit()', self.stop)

  def __del__(self):
    self.stop()
    super(SmartDICOMReceiver, self).__del__()

  def reset(self):
    self.currentStatus = ""
    self._running = False

  def connectEvents(self):
    self.directoryWatcher.addEventObserver(self.IncomingDataReceiveFinishedEvent, self.onDataReceivedFinished)
    self.directoryWatcher.addEventObserver(self.IncomingFileCountChangedEvent, self.onIncomingFileCountChanged)

  @vtk.calldata_type(vtk.VTK_STRING)
  def onDataReceivedFinished(self, caller, event, callData):
    self._updateStatus("{}: DICOM data receive completed.".format(self.NAME))
    self.invokeEvent(self.IncomingDataReceiveFinishedEvent, callData)

  @vtk.calldata_type(vtk.VTK_INT)
  def onIncomingFileCountChanged(self, caller, event, callData):
    status = "{}: Received {} files".format(self.NAME, callData)
    self._updateStatus(status)
    self.invokeEvent(self.IncomingFileCountChangedEvent, callData)

  def _updateStatus(self, text):
    if text != self.currentStatus:
      self.currentStatus = text
      self.invokeEvent(self.StatusChangedEvent, text)

  def isRunning(self):
    return self._running

  def forceStatusChangeEventUpdate(self):
    self.currentStatus = "Force update"
    self.refreshCurrentStatus()

  def start(self, runStoreSCP=True):
    self.stop()
    self.directoryWatcher.start()
    if runStoreSCP:
      self.startStoreSCP()
    self.invokeEvent(self.DICOMReceiverStartedEvent)
    self._running = True
    self.refreshCurrentStatus()

  def refreshCurrentStatus(self):
    statusText = ""
    if self._running:
      statusText = "{}: Waiting for incoming DICOM data".format(self.NAME) if self.storeSCPProcess else \
                   "{}: Watching incoming data directory only (no storescp running)".format(self.NAME)
    self._updateStatus(statusText)

  def stop(self):
    if self._running:
      self.directoryWatcher.stop()
      self.stopStoreSCP()
      self.reset()
      self.invokeEvent(self.DICOMReceiverStoppedEvent)

  def startStoreSCP(self):
    self.stopStoreSCP()
    self.storeSCPProcess = DICOMLib.DICOMStoreSCPProcess(incomingDataDir=self.incomingDataDirectory)
    self.storeSCPProcess.start()

  def stopStoreSCP(self):
    if self.storeSCPProcess:
      self.storeSCPProcess.stop()
      self.storeSCPProcess = None


class SliceAnnotation(object):

  ALIGN_LEFT = "left"
  ALIGN_CENTER = "center"
  ALIGN_RIGHT = "right"
  ALIGN_TOP = "top"
  ALIGN_BOTTOM = "bottom"
  POSSIBLE_VERTICAL_ALIGN = [ALIGN_TOP, ALIGN_CENTER, ALIGN_BOTTOM]
  POSSIBLE_HORIZONTAL_ALIGN = [ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT]

  @property
  def fontSize(self):
    return self._fontSize

  @fontSize.setter
  def fontSize(self, size):
    self._fontSize = size
    if self.textProperty:
      self.textProperty.SetFontSize(self.fontSize)
      self.textActor.SetTextProperty(self.textProperty)
    self.update()

  @property
  def textProperty(self):
    if not self.textActor:
      return None
    return self.textActor.GetTextProperty()

  @textProperty.setter
  def textProperty(self, textProperty):
    assert issubclass(textProperty, vtk.vtkTextProperty)
    self.textActor.SetTextProperty(textProperty)
    self.update()

  @property
  def opacity(self):
    if self.textProperty:
      return self.textProperty.GetOpacity()
    return None

  @opacity.setter
  def opacity(self, value):
    if not self.textProperty:
      return
    self.textProperty.SetOpacity(value)
    self.update()

  @property
  def color(self):
    if self.textProperty:
      return self.textProperty.GetColor()

  @color.setter
  def color(self, value):
    assert type(value) is tuple and len(value) == 3
    if self.textProperty:
      self.textProperty.SetColor(value)
      self.update()

  @property
  def verticalAlign(self):
    return self._verticalAlign

  @verticalAlign.setter
  def verticalAlign(self, value):
    if value not in self.POSSIBLE_VERTICAL_ALIGN:
      raise ValueError("Value %s is not allowed for vertical alignment. Only the following values are allowed: %s"
                       % (str(value), str(self.POSSIBLE_VERTICAL_ALIGN)))
    else:
      self._verticalAlign = value

  @property
  def horizontalAlign(self):
    return self._horizontalAlign

  @horizontalAlign.setter
  def horizontalAlign(self, value):
    if value not in self.POSSIBLE_HORIZONTAL_ALIGN:
      raise ValueError("Value %s is not allowed for horizontal alignment. Only the following values are allowed: %s"
                       % (str(value), str(self.POSSIBLE_HORIZONTAL_ALIGN)))
    else:
      self._horizontalAlign = value

  @property
  def renderer(self):
    return self.sliceView.renderWindow().GetRenderers().GetItemAsObject(0)

  def __init__(self, widget, text, **kwargs):
    self.observer = None
    self.textActor = None
    self.text = text

    self.sliceWidget = widget
    self.sliceView = widget.sliceView()
    self.sliceLogic = widget.sliceLogic()
    self.sliceNode = self.sliceLogic.GetSliceNode()
    self.sliceNodeDimensions = self.sliceNode.GetDimensions()

    self.xPos = kwargs.pop('xPos', 0)
    self.yPos = kwargs.pop('yPos', 0)

    self.initialFontSize = kwargs.pop('fontSize', 20)
    self.fontSize = self.initialFontSize
    self.textColor = kwargs.pop('color', (1, 0, 0))
    self.textBold = kwargs.pop('bold', 1)
    self.textShadow = kwargs.pop('shadow', 1)
    self.textOpacity = kwargs.pop('opacity', 1.0)
    self.verticalAlign = kwargs.pop('verticalAlign', 'center')
    self.horizontalAlign = kwargs.pop('horizontalAlign', 'center')

    self.createTextActor()

  def show(self):
    self.fitIntoViewport()
    self._addActor()
    self._addObserver()
    self.sliceView.update()

  def hide(self):
    self.remove()

  def remove(self):
    self._removeObserver()
    self._removeActor()
    self.sliceView.update()

  def _addObserver(self):
    if not self.observer and self.sliceNode:
      self.observer = self.sliceNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.modified)

  def _removeObserver(self):
    if self.observer:
      self.sliceNode.RemoveObserver(self.observer)
      self.observer = None

  def _removeActor(self):
    try:
      self.renderer.RemoveActor(self.textActor)
      self.update()
    except:
      pass

  def _addActor(self):
    self.renderer.AddActor(self.textActor)
    self.update()

  def update(self):
    self.sliceView.update()

  def createTextActor(self):
    self.textActor = vtk.vtkTextActor()
    self.textActor.SetInput(self.text)
    self.textProperty.SetFontSize(self.fontSize)
    self.textProperty.SetColor(self.textColor)
    self.textProperty.SetBold(self.textBold)
    self.textProperty.SetShadow(self.textShadow)
    self.textProperty.SetOpacity(self.textOpacity)
    self.textActor.SetTextProperty(self.textProperty)
    self.show()

  def applyPositioning(self):
    xPos = self.applyHorizontalAlign()
    yPos = self.applyVerticalAlign()
    self.textActor.SetDisplayPosition(xPos, yPos)

  def applyHorizontalAlign(self):
    centerX = int((self.sliceView.width - self.getFontWidth()) / 2)
    if self.xPos:
      xPos = self.xPos if 0 < self.xPos < centerX else centerX
    else:
      if self.horizontalAlign == self.ALIGN_LEFT:
        xPos = 0
      elif self.horizontalAlign == self.ALIGN_CENTER:
        xPos = centerX
      elif self.horizontalAlign == self.ALIGN_RIGHT:
        xPos = self.sliceView.width - self.getFontWidth()
    return int(xPos)

  def applyVerticalAlign(self):
    centerY = int((self.sliceView.height - self.getFontHeight()) / 2)
    if self.yPos:
      yPos = self.yPos if 0 < self.yPos < centerY else centerY
    else:
      if self.verticalAlign == self.ALIGN_TOP:
        yPos = self.sliceView.height - self.getFontHeight()
      elif self.verticalAlign == self.ALIGN_CENTER:
        yPos = centerY
      elif self.verticalAlign == self.ALIGN_BOTTOM:
        yPos = 0
    return int(yPos)

  def modified(self, observee, event):
    if event != "ModifiedEvent":
      return
    currentDimensions = observee.GetDimensions()
    if currentDimensions != self.sliceNodeDimensions:
      self.fitIntoViewport()
      self.update()
      self.sliceNodeDimensions = currentDimensions

  def getFontWidth(self):
    return self.getFontDimensions()[0]

  def getFontHeight(self):
    return self.getFontDimensions()[1]

  def getFontDimensions(self):
    size = [0.0, 0.0]
    self.textActor.GetSize(self.renderer, size)
    return size

  def fitIntoViewport(self):
    while self.getFontWidth() < self.sliceView.width and self.fontSize < self.initialFontSize:
      self.fontSize += 1
    while self.getFontWidth() > self.sliceView.width:
      self.fontSize -= 1
    self.applyPositioning()


class DICOMDirectorySender(DICOMProcess):
  """Code to send files/directories to a remote host (uses storescu from dcmtk)
  """

  STORESCU_PROCESS_FILE_NAME = "storescu"


  def __init__(self, directory, address, port, progressCallback=None):
    super(DICOMDirectorySender, self).__init__()
    self.directory = directory
    self.address = address
    self.port = port
    self.progressCallback = progressCallback
    if not self.progressCallback:
      self.progressCallback = self.defaultProgressCallback
    self.send()

    self.storescuExecutable = os.path.join(self.exeDir, self.STORESCU_PROCESS_FILE_NAME + self.exeExtension)

  def __del__(self):
    super(DICOMDirectorySender,self).__del__()

  def onStateChanged(self, newState):
    stdout, stderr = super(DICOMDirectorySender, self).onStateChanged(newState)
    if stderr and stderr.size():
      slicer.util.errorDisplay("An error occurred. For further information click 'Show Details...'",
                               windowTitle=self.__class__.__name__, detailedText=str(stderr))
    return stdout, stderr

  def defaultProgressCallback(self,s):
    print(s)

  def send(self):
    self.progressCallback("Starting send to %s:%s" % (self.address, self.port))
    self.start()
    self.progressCallback("Sent %s to %s:%s" % (self.directory, self.address, self.port))

  def start(self, cmd=None, args=None):
    self.storeSCUExecutable = os.path.join(self.exeDir, 'storescu'+self.exeExtension)
    # TODO: check pattern,,, .DS_Store exclusion
    args = [str(self.address), str(self.port), "-aec", "CTK", "--scan-directories", "--recurse", "--scan-pattern" ,
            "*[0-9a-Z]", self.directory]
    super(DICOMDirectorySender,self).start(self.storeSCUExecutable, args)
    self.process.connect('readyReadStandardOutput()', self.readFromStandardOutput)

  def readFromStandardOutput(self, readLineCallback=None):
    print('================ready to read stdout from %s===================' % self.__class__.__name__)
    while self.process.canReadLine():
      line = str(self.process.readLine())
      print("From %s: %s" % (self.__class__.__name__, line))
      if readLineCallback:
        readLineCallback(line)
    print('================end reading stdout from %s===================' % self.__class__.__name__)
    self.readFromStandardError()

  def readFromStandardError(self):
    stdErr = str(self.process.readAllStandardError())
    if stdErr:
      print('================ready to read stderr from %s===================' % self.__class__.__name__)
      print ("processed stderr: %s" %stdErr)
      print('================end reading stderr from %s===================' % self.__class__.__name__)


class WatchBoxAttribute(object):

  MASKED_PLACEHOLDER = "X"
  TRUNCATE_LENGTH = None

  @property
  def title(self):
    return self.titleLabel.text

  @title.setter
  def title(self, value):
    self.titleLabel.text = value if value else ""

  @property
  def masked(self):
    return self._masked

  @masked.setter
  def masked(self, value):
    if self._masked == value:
      return
    self._masked = value
    self.updateVisibleValues(self.originalValue if not self.masked else self.maskedValue(self.originalValue))

  @property
  def value(self):
    return self.valueLabel.text

  @value.setter
  def value(self, value):
    if not value:
      value = ""
    if type(value) not in [str, unicode]:
      value = str(value)
    self.originalValue = value
    self.updateVisibleValues(self.originalValue if not self.masked else self.maskedValue(self.originalValue))

  @property
  def originalValue(self):
    return self._value

  @originalValue.setter
  def originalValue(self, value):
    self._value = value

  def __init__(self, name, title, tags=None, masked=False, callback=None):
    self.name = name
    self._masked = masked
    self.titleLabel = qt.QLabel()
    self.titleLabel.setStyleSheet("QLabel{ font-weight: bold;}")
    self.valueLabel = qt.QLabel()
    self.title = title
    self.callback = callback
    self.tags = None if not tags else tags if type(tags) is list else [str(tags)]
    self.value = None

  def updateVisibleValues(self, value):
    self.valueLabel.text = value[0:self.TRUNCATE_LENGTH]+"..." if self.TRUNCATE_LENGTH and \
                                                                  len(value) > self.TRUNCATE_LENGTH else value
    self.valueLabel.toolTip = value

  def maskedValue(self, value):
    return self.MASKED_PLACEHOLDER * len(value)


class WindowLevelEffect(object):

  EVENTS = [vtk.vtkCommand.LeftButtonPressEvent,
            vtk.vtkCommand.LeftButtonReleaseEvent,
            vtk.vtkCommand.MouseMoveEvent]

  def __init__(self, sliceWidget):
    self.actionState = None
    self.startXYPosition = None
    self.currentXYPosition = None
    self.cursor = self._createWLCursor()

    self.sliceWidget = sliceWidget
    self.sliceLogic = sliceWidget.sliceLogic()
    self.compositeNode = sliceWidget.mrmlSliceCompositeNode()
    self.sliceView = self.sliceWidget.sliceView()
    self.interactor = self.sliceView.interactorStyle().GetInteractor()

    self.actionState = None

    self.interactorObserverTags = []

    self.bgStartWindowLevel = [0,0]
    self.fgStartWindowLevel = [0,0]

  def _createWLCursor(self):
    iconPath = os.path.join(os.path.dirname(sys.modules[self.__module__].__file__),
                            '../Resources/Icons/cursor-window-level.png')
    pixmap = qt.QPixmap(iconPath)
    return qt.QCursor(qt.QIcon(pixmap).pixmap(32, 32), 0, 0)

  def enable(self):
    for e in self.EVENTS:
      tag = self.interactor.AddObserver(e, self._processEvent, 1.0)
      self.interactorObserverTags.append(tag)

  def disable(self):
    for tag in self.interactorObserverTags:
      self.interactor.RemoveObserver(tag)
    self.interactorObserverTags = []

  def _processEvent(self, caller=None, event=None):
    """
    handle events from the render window interactor
    """
    bgLayer = self.sliceLogic.GetBackgroundLayer()
    fgLayer = self.sliceLogic.GetForegroundLayer()

    bgNode = bgLayer.GetVolumeNode()
    fgNode = fgLayer.GetVolumeNode()

    changeFg = 1 if fgNode and self.compositeNode.GetForegroundOpacity() > 0.5 else 0
    changeBg = not changeFg

    if event == "LeftButtonPressEvent":
      self.actionState = "dragging"
      self.sliceWidget.setCursor(self.cursor)

      xy = self.interactor.GetEventPosition()
      self.startXYPosition = xy
      self.currentXYPosition = xy

      if bgNode:
        bgDisplay = bgNode.GetDisplayNode()
        self.bgStartWindowLevel = [bgDisplay.GetWindow(), bgDisplay.GetLevel()]
      if fgNode:
        fgDisplay = fgNode.GetDisplayNode()
        self.fgStartWindowLevel = [fgDisplay.GetWindow(), fgDisplay.GetLevel()]
      self._abortEvent(event)

    elif event == "MouseMoveEvent":
      if self.actionState == "dragging":
        if bgNode and changeBg:
          self._updateNodeWL(bgNode, self.bgStartWindowLevel, self.startXYPosition)
        if fgNode and changeFg:
          self._updateNodeWL(fgNode, self.fgStartWindowLevel, self.startXYPosition)
        self._abortEvent(event)

    elif event == "LeftButtonReleaseEvent":
      self.sliceWidget.unsetCursor()
      self.actionState = ""
      self._abortEvent(event)

  def _updateNodeWL(self, node, startWindowLevel, startXY):

    currentXY = self.interactor.GetEventPosition()

    vDisplay = node.GetDisplayNode()
    vImage = node.GetImageData()
    vRange = vImage.GetScalarRange()

    deltaX = currentXY[0]-startXY[0]
    deltaY = currentXY[1]-startXY[1]
    gain = (vRange[1]-vRange[0])/500.
    newWindow = startWindowLevel[0]+(gain*deltaX)
    newLevel = startWindowLevel[1]+(gain*deltaY)

    vDisplay.SetAutoWindowLevel(0)
    vDisplay.SetWindowLevel(newWindow, newLevel)
    vDisplay.Modified()

  def _abortEvent(self, event):
    """Set the AbortFlag on the vtkCommand associated
    with the event - causes other things listening to the
    interactor not to receive the events"""
    # TODO: make interactorObserverTags a map to we can
    # explicitly abort just the event we handled - it will
    # be slightly more efficient
    for tag in self.interactorObserverTags:
      cmd = self.interactor.GetCommand(tag)
      cmd.SetAbortFlag(1)