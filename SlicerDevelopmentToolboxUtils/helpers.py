import ast
import logging
import os
import sys
import urllib
from urllib import FancyURLopener

import vtk
import qt
import slicer
from DICOMLib import DICOMProcess, DICOMStoreSCPProcess

from events import SlicerDevelopmentToolboxEvents
from mixins import ModuleWidgetMixin, ModuleLogicMixin, ParameterNodeObservationMixin


class SampleDataDownloader(FancyURLopener, ParameterNodeObservationMixin):
  """ Helper class for retrieving sample data from an url """

  StatusChangedEvent = SlicerDevelopmentToolboxEvents.StatusChangedEvent
  """ Invoked whenever the current status changed """
  CanceledEvent = SlicerDevelopmentToolboxEvents.CanceledEvent
  """ Invoked if download was canceled """
  FinishedEvent = SlicerDevelopmentToolboxEvents.FinishedEvent
  """ Invoked once download was finished """
  FailedEvent = SlicerDevelopmentToolboxEvents.FailedEvent
  """ Invoked if download failed """

  def __init__(self, enableLogging=False):
    super(SampleDataDownloader, self).__init__()
    self._loggingEnabled = enableLogging
    self.isDownloading = False
    self.resetAndInitialize()

  def __del__(self):
    super(SampleDataDownloader, self).__del__()

  def resetAndInitialize(self):
    """ Resetting and reinitializing class members. Cancels download if there is one currently running. """
    self._canceled=False
    if self.isDownloading:
      self.cancelDownload()
    self.removeEventObservers()
    if self._loggingEnabled:
      self._addOwnObservers()

  def cancelDownload(self):
    """ Cancels the download """
    self._canceled = True

  def wasCanceled(self):
    """ Returns boolean value stating if download has been canceled

    Returns:
      bool: True if download was canceled. Otherwise False.
    """
    return self._canceled

  def downloadFileIntoCache(self, uri, name):
    """ Downloads data from url into the local filesystem cache with the given filename

    Params:
      url(str): url to retrieve the data from
      filename(str): filename of the downloaded data on the local filesystem

    Returns:
      filePath(str): path to the downloaded data on the local filesystem
    """
    return self.downloadFile(uri, slicer.mrmlScene.GetCacheManager().GetRemoteCacheDirectory(), name)

  def downloadFile(self, url, destinationDirectory, filename):
    """ Downloads data from url into the given destination directory with the given filename

    Params:
      url(str): url to retrieve the data from
      destinationDirectory(str): destination directory where to store the data on the local filesystem
      filename(str): filename of the downloaded data on the local filesystem

    Returns:
      filePath(str): path to the downloaded data on the local filesystem
    """
    if self.isDownloading:
      self.cancelDownload()
    self._canceled = False
    filePath = os.path.join(destinationDirectory, filename)
    if not os.path.exists(filePath) or os.stat(filePath).st_size == 0:
      self.downloadPercent = 0
      self.invokeEvent(self.StatusChangedEvent, str(['Requesting download %s from %s...' % (filename, url),
                                                     self.downloadPercent]))
      try:
        self.isDownloading = True
        self.retrieve(url, filePath, self._reportHook)
        self.invokeEvent(self.StatusChangedEvent, str(['Download finished', self.downloadPercent]))
      except IOError as e:
        self.invokeEvent(self.FailedEvent, str(['Download failed: %s' % e, self.downloadPercent]))
    else:
      self.invokeEvent(self.StatusChangedEvent, str(['File already exists in cache - reusing it.', 100]))
    return filePath

  def retrieve(self, url, filename=None, reporthook=None, data=None):
    """ Retrieves data from the given url and returns a tuple of filename and headers

    Args:
      url (str): url of the data to be retrieved
      filename (str, optional): filename from the url to download
      reporthook: (function, optional): function that should be called for e.g. keeping an UI updated with current state
      data (, optional):

    Returns:
      result: (filename, headers)

    See Also:
        urllib.URLopener
    """
    self._canceled=False
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
        while not self._canceled:
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

    if self._canceled and os.path.exists(filename):
      os.remove(filename)
    return result

  def _addOwnObservers(self):
    for event in [self.StatusChangedEvent, self.CanceledEvent,
                  self.FailedEvent, self.FinishedEvent]:
      self.addEventObserver(event, self._logMessage)

  @vtk.calldata_type(vtk.VTK_STRING)
  def _logMessage(self, caller, event, callData):
    message, _ = ast.literal_eval(callData)
    logging.debug(message)

  def _humanReadableFormatSize(self, size):
    """ See Also: from http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    """
    for x in ['bytes', 'KB', 'MB', 'GB']:
      if -1024.0 < size < 1024.0:
        return "%3.1f %s" % (size, x)
      size /= 1024.0
    return "%3.1f %s" % (size, 'TB')

  def _reportHook(self, blocksSoFar, blockSize, totalSize):
    percent = min(int((100. * blocksSoFar * blockSize) / totalSize), 100)
    humanSizeSoFar = self._humanReadableFormatSize(min(blocksSoFar * blockSize, totalSize))
    humanSizeTotal = self._humanReadableFormatSize(totalSize)
    self.downloadPercent = percent
    self.invokeEvent(self.StatusChangedEvent, str(['Downloaded %s (%d%% of %s)...' % (humanSizeSoFar, percent,
                                                                                      humanSizeTotal),
                                                   self.downloadPercent]))


class DirectoryObserver(ModuleLogicMixin):
  """ Helper class for observing a given directory by checking the filecount every n milliseconds

  Args:
    directory(str): directory to be observed
    every(int, optional): time in milliseconds defining how often to check the filecount
  """

  @property
  def running(self):
    """ Returns if observation of directory is currently active

    Returns:
       bool: True if running else False
    """
    return getattr(self, "_running", False)

  StartedEvent = SlicerDevelopmentToolboxEvents.StartedEvent
  """ Invoked when DirectoryObserver starts observing directory """
  StoppedEvent = SlicerDevelopmentToolboxEvents.StoppedEvent
  """ Invoked when DirectoryObserver stops observing directory """
  FileCountChangedEvent = SlicerDevelopmentToolboxEvents.FileCountChangedEvent
  """ Invoked when filecount of the observed directory changed """

  def __init__(self, directory, every=1000):
    self._directory = directory
    self._every = every
    self._setupTimer()
    self.reset()

  def __del__(self):
    self.reset()
    super(DirectoryObserver, self).__del__()

  def reset(self):
    """ Resets class members and stops DirectoryObserver if it is observing a directory """
    self._initialFileList = []
    self._currentFileList = []
    self._currentStatus = ""
    if self.running:
      self.stop()

  def isRunning(self):
    """ Returns state if DirectoryObserver is observing

    Returns:
       bool: True if DirectoryObserver is currently observing a directory, otherwise False
    """
    return self.running

  def start(self):
    """ Starts observing the directory and invokes StartedEvent """
    self.stop()
    self._initialFileList = self.getFileList(self._directory)
    self._lastFileCount = len(self._initialFileList)
    self._running = True
    self._startObserving()
    self.invokeEvent(self.StartedEvent)

  def stop(self):
    """ Stops observing the directory (if observing is currently running) and invokes StoppedEvent """
    if self.running:
      self.observingTimer.stop()
      self._running = False
      self.reset()
      self.invokeEvent(self.StoppedEvent)

  def _setupTimer(self):
    self.observingTimer = self.createTimer(interval=self._every, slot=self._startObserving, singleShot=True)

  def _startObserving(self):
    if not self.running:
      return
    self._currentFileList = self.getFileList(self._directory)
    currentFileListCount = len(self._currentFileList)
    if self._lastFileCount != currentFileListCount:
      self._onFileCountChanged(currentFileListCount)
    else:
      self._onFileCountUnchanged()

  def _onFileCountUnchanged(self):
    self.observingTimer.start()

  def _onFileCountChanged(self, currentFileListCount):
    self._lastFileCount = currentFileListCount
    newFileCount = abs(len(self._initialFileList) - currentFileListCount)
    self.invokeEvent(self.FileCountChangedEvent, newFileCount)
    self.observingTimer.start()


class TimeoutDirectoryObserver(DirectoryObserver):
  """ Observes a directory and fires event if filecount changed once and is unchanged for a period of time (timeout)

  The observation timeout is useful when receiving DICOM data via storescp process since there is no sign of a finished
  reception. One indicator for this can be the unchanged filecount for a period of time. The timeout defines a period
  of time that TimeoutDirectoryObserver waits until it checks the filecount again and invokes the event in case it is
  still unchanged.

  Args:
    directory(str): directory to be observed
    timeout(str, optional): time in milliseconds Default is 5000

  See Also:
    :paramref:`SlicerDevelopmentToolboxUtils.helpers.DirectoryObserver`

  """

  IncomingDataReceiveFinishedEvent = SlicerDevelopmentToolboxEvents.FinishedEvent
  """ Invoked after timeout exceeded and filecount is unchanged for the time of timeout """

  def __init__(self, directory, timeout=5000):
    self.receiveFinishedTimeout = timeout
    super(TimeoutDirectoryObserver, self).__init__(directory)

  def _setupTimer(self):
    super(TimeoutDirectoryObserver, self)._setupTimer()
    self._timeoutTimer = self.createTimer(interval=5000, slot=self._checkIfStillSameFileCount, singleShot=True)

  def stop(self):
    if self.running:
      self._timeoutTimer.stop()
    super(TimeoutDirectoryObserver, self).stop()

  def _onFileCountUnchanged(self):
    currentFileListCount = len(self._currentFileList)
    if currentFileListCount != len(self._initialFileList):
      self._lastFileCount = currentFileListCount
      self._timeoutTimer.start()
    else:
      self.observingTimer.start()

  def _checkIfStillSameFileCount(self):
    self._currentFileList = self.getFileList(self._directory)
    if self._lastFileCount == len(self._currentFileList):
      newFileList = list(set(self._currentFileList) - set(self._initialFileList))
      self._initialFileList = self._currentFileList
      self._lastFileCount = len(self._initialFileList)
      if len(newFileList):
        self.invokeEvent(self.IncomingDataReceiveFinishedEvent, str(newFileList))
    self.observingTimer.start()


class SmartDICOMReceiver(ModuleLogicMixin):
  """ SmartDICOMReceiver combines storescp with an observation of changes within the destination directory

  Since storescp is not giving any feedback about a finished transfer, SmartDICOMReceiver combines storescp with the
  observation process provided by the TimeoutDirectoryObserver. By using a timeout, SmartDICOMReceiver knows when a
  transfer is finished unless there are other reasons for a failed transfer.

  Args:
    destinationDirectory(str): destination directory for reception of DICOM images
    incomingPort(str or int, optional): port on which incoming date is expected to get received Default port is 11112

  .. code-block:: python

    import os
    import vtk
    import shutil
    from SlicerDevelopmentToolboxUtils.mixins import ModuleLogicMixin
    from SlicerDevelopmentToolboxUtils.helpers import SmartDICOMReceiver

    @vtk.calldata_type(vtk.VTK_INT)
    def onFileCountChanged(caller, event, callData):
      print "Received %d files" % callData

    inputPath = os.path.join(slicer.app.temporaryPath, "SmartDICOMReceiverTest")
    ModuleLogicMixin.createDirectory(inputPath)

    dicomReceiver = SmartDICOMReceiver(inputPath, incomingPort=11112)
    dicomReceiver.addEventObserver(dicomReceiver.FileCountChangedEvent, onFileCountChanged)
    dicomReceiver.start()

    # then send some data....

    dicomReceiver.stop()
    shutil.rmtree(inputPath)

  """

  _NAME = "SmartDICOMReceiver"
  _STATUS_RECEIVING = "{}: Receiving DICOM data".format(_NAME)

  StatusChangedEvent = SlicerDevelopmentToolboxEvents.StatusChangedEvent
  """ Invoked whenever status is updated """
  StartedEvent = SlicerDevelopmentToolboxEvents.StartedEvent
  """ Invoked after SmartDICOMReceiver is started (with or without storescp) """
  StoppedEvent = SlicerDevelopmentToolboxEvents.StoppedEvent
  """ Invoked after SmartDICOMReceiver is stopped """
  IncomingDataReceiveFinishedEvent = TimeoutDirectoryObserver.IncomingDataReceiveFinishedEvent
  """ Invoked when DICOM images has been received """
  FileCountChangedEvent = TimeoutDirectoryObserver.FileCountChangedEvent
  """ Invoked when filecount of the destination directory changed """

  def __init__(self, destinationDirectory, incomingPort=None):
    self.destinationDirectory = destinationDirectory
    self._directoryObserver = TimeoutDirectoryObserver(destinationDirectory)
    self._connectEvents()
    self._storeSCPProcess = None
    self._incomingPort = None if not incomingPort else int(incomingPort)
    self.reset()
    slicer.app.connect('aboutToQuit()', self.stop)

  def __del__(self):
    self.stop()
    super(SmartDICOMReceiver, self).__del__()

  def reset(self):
    self.currentStatus = ""
    self._running = False

  def isRunning(self):
    """ Returns state if SmartDICOMReceiver is currently running

    Returns:
       bool: True if SmartDICOMReceiver is currently running, otherwise False
    """
    return self._running

  def start(self, runStoreSCP=True):
    """ Starts observation process of the destination directory and storescp if specified and invokes StartedEvent

    Args:
       runStoreSCP(bool,optional): specifies if storescp process should be started. Default value is set to True
    """
    self.stop()
    self._directoryObserver.start()
    if runStoreSCP:
      self._startStoreSCP()
    self.invokeEvent(self.StartedEvent)
    self._running = True
    self._refreshCurrentStatus()

  def stop(self):
    """ Stops observation and storescp process and invokes StoppedEvent """
    if self._running:
      self._directoryObserver.stop()
      self.stopStoreSCP()
      self.reset()
      self.invokeEvent(self.StoppedEvent)

  def stopStoreSCP(self):
    """ Stopping the storescp process only without stopping the observation process """
    if self._storeSCPProcess:
      self._storeSCPProcess.stop()
      self._storeSCPProcess = None

  def forceStatusChangeEventUpdate(self):
    """ Forces a current status update to be invoked with the current status """
    self.currentStatus = "Force update"
    self._refreshCurrentStatus()

  def _startStoreSCP(self):
    self.stopStoreSCP()
    self._storeSCPProcess = DICOMStoreSCPProcess(incomingDataDir=self.destinationDirectory,
                                                 incomingPort=self._incomingPort)
    self._storeSCPProcess.start()

  def _connectEvents(self):
    self._directoryObserver.addEventObserver(self.IncomingDataReceiveFinishedEvent, self._onDataReceptionFinished)
    self._directoryObserver.addEventObserver(self.FileCountChangedEvent, self._onFileCountChanged)

  @vtk.calldata_type(vtk.VTK_STRING)
  def _onDataReceptionFinished(self, caller, event, callData):
    self._updateStatus("{}: DICOM data receive completed.".format(self._NAME))
    self.invokeEvent(self.IncomingDataReceiveFinishedEvent, callData)

  @vtk.calldata_type(vtk.VTK_INT)
  def _onFileCountChanged(self, caller, event, callData):
    status = "{}: Received {} files".format(self._NAME, callData)
    self._updateStatus(status)
    self.invokeEvent(self.FileCountChangedEvent, callData)

  def _updateStatus(self, text):
    if text != self.currentStatus:
      self.currentStatus = text
      self.invokeEvent(self.StatusChangedEvent, text)

  def _refreshCurrentStatus(self):
    statusText = ""
    if self._running:
      statusText = "{}: Waiting for incoming DICOM data".format(self._NAME) if self._storeSCPProcess else \
                   "{}: Watching incoming data directory only (no storescp running)".format(self._NAME)
    self._updateStatus(statusText)


class SliceAnnotationHandlerBase(ModuleWidgetMixin):
  """ Base class for handling slice annotations for different situation (e.g. steps)

  Holds all slice annotations and keeps track of removing them all when requested. Method addSliceAnnotations needs to
  be implemented.

  """

  def __init__(self):
    self.sliceAnnotations = []
    self._setupSliceWidgets()

  def cleanup(self):
    """ Removes slice annotations """
    self.removeSliceAnnotations()

  def _setupSliceWidgets(self):
    self.createSliceWidgetClassMembers("Red")
    self.createSliceWidgetClassMembers("Yellow")
    self.createSliceWidgetClassMembers("Green")

  def addSliceAnnotations(self):
    """ Keeps track of adding slice annotations at the right time (e.g. different layouts - different annotations)

    Note:
      This method must be implemented by inheriting classes
    """
    raise NotImplementedError

  def removeSliceAnnotations(self):
    while len(self.sliceAnnotations):
      annotation = self.sliceAnnotations.pop()
      annotation.remove()


class SliceAnnotation(object):
  """ Represents a text to a slice widget/view.

  Besides defining which text should be displayed within the slice widget at which position a variety of other
  properties can be defined listed as keyword arguments.

  Note: The annotation is automatically resized if it doesn't fit into the slice widget.

  Args:
    widget(qMRMLSliceWidget): slice widget to show text on
    text(str): text to display on slice widget

  :Keyword Arguments:
    * *xPos* (``int``)
    * *yPos* (``int``)
    * *size* (``int``) -- Default: 20
    * *color* (``tuple``) -- rgb color. Default: (1.0, 0.0 ,0.0)
    * *bold* (``int``) -- Default: 1
    * *shadow* (``int``) -- Default: 1
    * *opacity* (``float``) -- Default: 1.0
    * *verticalAlign* (``str``) -- one of POSSIBLE_VERTICAL_ALIGN. Default: "center"
    * *horizontalAlign* (``str``) -- one of POSSIBLE_HORIZONTAL_ALIGN. Default: "center"

  .. code-block:: python

    from SlicerDevelopmentToolboxUtils.helpers import SliceAnnotation

    kwargs = {"yPos":55, "size":30}
    redWidget = slicer.app.layoutManager().sliceWidget("Red")
    text = "Testing the display of annotations"
    annotation = SliceAnnotation(redWidget, text, **kwargs)

    annotation.size = 50

    # then try
    annotation.hide()

  """

  ALIGN_LEFT = "left"
  """ Alignment left """
  ALIGN_CENTER = "center"
  """ Alignment center """
  ALIGN_RIGHT = "right"
  """ Alignment right """
  ALIGN_TOP = "top"
  """ Alignment top """
  ALIGN_BOTTOM = "bottom"
  """ Alignment bottom """
  POSSIBLE_VERTICAL_ALIGN = [ALIGN_TOP, ALIGN_CENTER, ALIGN_BOTTOM]
  POSSIBLE_HORIZONTAL_ALIGN = [ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT]

  @property
  def size(self):
    """ Font size of the text """
    return self._size

  @size.setter
  def size(self, size):
    self._initialSize = size
    self._size = size
    self._update()

  @property
  def textProperty(self):
    """ vtk.vtkTextProperty presenting properties for the text to be displayed"""
    if not self.textActor:
      return None
    return self.textActor.GetTextProperty()

  @textProperty.setter
  def textProperty(self, textProperty):
    assert issubclass(textProperty, vtk.vtkTextProperty)
    self.textActor.SetTextProperty(textProperty)
    self._update()

  @property
  def opacity(self):
    """ Text opacity """
    if self.textProperty:
      return self.textProperty.GetOpacity()
    return None

  @opacity.setter
  def opacity(self, value):
    if not self.textProperty:
      return
    self.textProperty.SetOpacity(value)
    self._update()

  @property
  def color(self):
    """ Text color """
    if self.textProperty:
      return self.textProperty.GetColor()

  @color.setter
  def color(self, value):
    assert type(value) is tuple and len(value) == 3
    if self.textProperty:
      self.textProperty.SetColor(value)
      self._update()

  @property
  def verticalAlign(self):
    """ Vertical align """
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
    """ Horizontal Align"""
    return self._horizontalAlign

  @horizontalAlign.setter
  def horizontalAlign(self, value):
    if value not in self.POSSIBLE_HORIZONTAL_ALIGN:
      raise ValueError("Value %s is not allowed for horizontal alignment. Only the following values are allowed: %s"
                       % (str(value), str(self.POSSIBLE_HORIZONTAL_ALIGN)))
    else:
      self._horizontalAlign = value

  @property
  def _renderer(self):
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

    self._initialSize = kwargs.pop('size', 20)
    self._size = self._initialSize
    self.textColor = kwargs.pop('color', (1.0, 0.0, 0.0))
    self.textBold = kwargs.pop('bold', 1)
    self.textShadow = kwargs.pop('shadow', 1)
    self.textOpacity = kwargs.pop('opacity', 1.0)
    self.verticalAlign = kwargs.pop('verticalAlign', 'center')
    self.horizontalAlign = kwargs.pop('horizontalAlign', 'center')

    self._createTextActor()

  def __del__(self):
    self.remove()

  def show(self):
    """ Displays the text within the slice widget """
    self._addActor()
    self._addObserver()
    self._update()

  def hide(self):
    """ Hides the text from the slice widget """
    self.remove()

  def remove(self):
    """ Hides the text from the slice widget """
    self._removeObserver()
    self._removeActor()
    self._update()

  def _addObserver(self):
    if not self.observer and self.sliceNode:
      self.observer = self.sliceNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self._onModified)

  def _removeObserver(self):
    if self.observer:
      self.sliceNode.RemoveObserver(self.observer)
      self.observer = None

  def _removeActor(self):
    try:
      self._renderer.RemoveActor(self.textActor)
      self._update()
    except:
      pass

  def _addActor(self):
    self._renderer.AddActor(self.textActor)
    self._update()

  def _update(self):
    if not self._fitIntoViewport(self._size):
      logging.debug("Font size is to large for slice widget. Decreasing.")
      self._decreaseSizeToFitViewport()
    self._applyPositioning()
    self.sliceView.update()

  def _createTextActor(self):
    self.textActor = vtk.vtkTextActor()
    self.textActor.SetInput(self.text)
    self.textProperty.SetColor(self.textColor)
    self.textProperty.SetBold(self.textBold)
    self.textProperty.SetShadow(self.textShadow)
    self.textProperty.SetOpacity(self.textOpacity)
    self.textActor.SetTextProperty(self.textProperty)
    self.size = self._initialSize
    self.show()

  def _applyPositioning(self):
    xPos = self._applyHorizontalAlign()
    yPos = self._applyVerticalAlign()
    self.textActor.SetDisplayPosition(xPos, yPos)

  def _applyHorizontalAlign(self):
    centerX = int((self.sliceView.width - self._getFontWidth()) / 2)
    if self.xPos:
      xPos = self.xPos if 0 < self.xPos < centerX else centerX
    else:
      if self.horizontalAlign == self.ALIGN_LEFT:
        xPos = 0
      elif self.horizontalAlign == self.ALIGN_CENTER:
        xPos = centerX
      elif self.horizontalAlign == self.ALIGN_RIGHT:
        xPos = self.sliceView.width - self._getFontWidth()
    return int(xPos)

  def _applyVerticalAlign(self):
    centerY = int((self.sliceView.height - self._getFontHeight()) / 2)
    if self.yPos:
      yPos = self.yPos if 0 < self.yPos < centerY else centerY
    else:
      if self.verticalAlign == self.ALIGN_TOP:
        yPos = self.sliceView.height - self._getFontHeight()
      elif self.verticalAlign == self.ALIGN_CENTER:
        yPos = centerY
      elif self.verticalAlign == self.ALIGN_BOTTOM:
        yPos = 0
    return int(yPos)

  def _onModified(self, caller, event):
    if event != "ModifiedEvent":
      return
    currentDimensions = caller.GetDimensions()
    if currentDimensions != self.sliceNodeDimensions:
      self._increaseSizeToFitViewport()
      self._update()
      self.sliceNodeDimensions = currentDimensions

  def _getFontWidth(self):
    return self._getFontDimensions()[0]

  def _getFontHeight(self):
    return self._getFontDimensions()[1]

  def _getFontDimensions(self):
    size = [0.0, 0.0]
    self.textActor.GetSize(self._renderer, size)
    return size

  def _fitIntoViewport(self, size):
    tempSize = self.textProperty.GetFontSize()
    self.textProperty.SetFontSize(size)
    self.textActor.SetTextProperty(self.textProperty)
    if self._getFontWidth() > self.sliceView.width:
      self.textProperty.SetFontSize(tempSize)
      self.textActor.SetTextProperty(self.textProperty)
      return False
    return True

  def _decreaseSizeToFitViewport(self):
    while not self._fitIntoViewport(self._size):
      self._size -= 1

  def _increaseSizeToFitViewport(self):
    while self._fitIntoViewport(self._size) and self._size < self._initialSize:
      self._size += 1


class DICOMDirectorySender(DICOMProcess):
  """ Send files/directories to a remote host (uses storescu from dcmtk)

  Args:
    directory(str): source directory to send data from
    address(str): destination address to send the data to
    port(int): destination port to send the data to
    progressCallback(function, optional): function that takes a string parameter. Default is None

  .. code-block:: python

    from SlicerDevelopmentToolboxUtils.helpers import SliceAnnotation

    source = #any directory
    dicomSender = DICOMDirectorySender(directory=source, address='localhost', port=11112)
    dicomSender.send()
  """

  _STORESCU_PROCESS_FILE_NAME = "storescu"

  def __init__(self, directory, address, port, progressCallback=None):
    super(DICOMDirectorySender, self).__init__()
    self.directory = directory
    self.address = address
    self.port = port
    self.progressCallback = progressCallback
    if not self.progressCallback:
      self.progressCallback = self._defaultProgressCallback
    self.send()

    self.storescuExecutable = os.path.join(self.exeDir, self._STORESCU_PROCESS_FILE_NAME + self.exeExtension)

  def __del__(self):
    super(DICOMDirectorySender,self).__del__()

  def onStateChanged(self, newState):
    stdout, stderr = super(DICOMDirectorySender, self).onStateChanged(newState)
    if stderr and stderr.size():
      slicer.util.errorDisplay("An error occurred. For further information click 'Show Details...'",
                               windowTitle=self.__class__.__name__, detailedText=str(stderr))
    return stdout, stderr

  def send(self):
    """ Starts the sending process """
    self.progressCallback("Starting send to %s:%s" % (self.address, self.port))
    self.start()
    self.progressCallback("Sent %s to %s:%s" % (self.directory, self.address, self.port))

  def start(self, cmd=None, args=None):
    """ Starts storescup executable """
    self.storeSCUExecutable = os.path.join(self.exeDir, 'storescu'+self.exeExtension)
    # TODO: check pattern,,, .DS_Store exclusion
    args = [str(self.address), str(self.port), "-aec", "CTK", "--scan-directories", "--recurse", "--scan-pattern" ,
            "*[0-9a-Z]", self.directory]
    super(DICOMDirectorySender,self).start(self.storeSCUExecutable, args)
    self.process.connect('readyReadStandardOutput()', self._readFromStandardOutput)

  def _defaultProgressCallback(self, s):
    print(s)

  def _readFromStandardOutput(self, readLineCallback=None):
    print('================ready to read stdout from %s===================' % self.__class__.__name__)
    while self.process.canReadLine():
      line = str(self.process.readLine())
      print("From %s: %s" % (self.__class__.__name__, line))
      if readLineCallback:
        readLineCallback(line)
    print('================end reading stdout from %s===================' % self.__class__.__name__)
    self._readFromStandardError()

  def _readFromStandardError(self):
    stdErr = str(self.process.readAllStandardError())
    if stdErr:
      print('================ready to read stderr from %s===================' % self.__class__.__name__)
      print ("processed stderr: %s" %stdErr)
      print('================end reading stderr from %s===================' % self.__class__.__name__)


class WatchBoxAttribute(object):
  """" A data structure for holding attribute information for displaying it within a BasicInformationWatchBox

  Class members tags (e.g. xml or DICOM) and callback are helpful for file based watch boxes

  Args:
    name(str): Name of the attribute
    title(str): Title to be displayed for the attribute
    tags(str or list(str), optional): Tags to retrieve information from i.e. when XML or DICOM is used as source
    masked(bool, optional): Enables the option to mask the displayed value for the attribute. Default is False
    callback(function, optional): Callback to retrieve the actual value from. Default is None

  See Also:
    :paramref:`SlicerDevelopmentToolboxUtils.widgets.BasicInformationWatchBox`

    :paramref:`SlicerDevelopmentToolboxUtils.widgets.FileBasedInformationWatchBox`

    :paramref:`SlicerDevelopmentToolboxUtils.widgets.XMLBasedInformationWatchBox`

    :paramref:`SlicerDevelopmentToolboxUtils.widgets.DICOMBasedInformationWatchBox`
  """

  MASKED_PLACEHOLDER = "X"
  """ Placeholder to display when masking is enabled to hide confidential information """
  TRUNCATE_LENGTH = None
  """ Maximum length a text should have. In case it's longer it will be truncated """

  @property
  def title(self):
    """ Title of the attribute to be displayed """
    return self.titleLabel.text

  @title.setter
  def title(self, value):
    self.titleLabel.text = value if value else ""

  @property
  def masked(self):
    """ Returns if masking is enabled."""
    return self._masked

  @masked.setter
  def masked(self, value):
    if self._masked == value:
      return
    self._masked = value
    self.updateVisibleValues(self.originalValue if not self.masked else self.maskedValue(self.originalValue))

  @property
  def value(self):
    """ Value of the attribute to be displayed.

    Note:
      This value can be masked
      """
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
    """ Original value of the attribute """
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
    """ Updates the v"""
    self.valueLabel.text = value[0:self.TRUNCATE_LENGTH]+"..." if self.TRUNCATE_LENGTH and \
                                                                  len(value) > self.TRUNCATE_LENGTH else value
    self.valueLabel.toolTip = value

  def maskedValue(self, value):
    """ Replacing the original value for displaying with MASKED_PLACEHOLDER

    Args:
      value(str): value that should get masked and returned
    Returns:
     str:
    """
    return self.MASKED_PLACEHOLDER * len(value)


class WindowLevelEffect(object):
  """ Enables windowing on a certain slice widget with respect to the opacity of foreground and background

  Windowing is applied to foreground if opacity is higher than 0.5. Otherwise windowing will be applied to the
  background

  Args:
    sliceWidget(qMRMLSliceWidget): slice widget to enabled the effect for

  .. code-block:: python

    from SlicerDevelopmentToolboxUtils.helpers import WindowLevelEffect

    redWidget = slicer.app.layoutManager().sliceWidget("Red")
    windowLevelEffect = WindowLevelEffect(redWidget)
    windowLevelEffect.enable()

    # windowLevelEffect.disable()

  """

  def __init__(self, sliceWidget):
    self.__actionState = None
    self.__startXYPosition = None
    self.__currentXYPosition = None
    self.__cursor = self._createWLCursor()

    self._sliceWidget = sliceWidget
    self._sliceLogic = sliceWidget.sliceLogic()
    self._compositeNode = sliceWidget.mrmlSliceCompositeNode()
    self._sliceView = self._sliceWidget.sliceView()
    self._interactor = self._sliceView.interactorStyle().GetInteractor()

    self.__actionState = None

    self._interactorObserverTags = []

    self._bgStartWindowLevel = [0, 0]
    self._fgStartWindowLevel = [0, 0]

  def enable(self):
    """ Enables WindowLevelEffect for the slice widget specified during initialization """
    for e in [vtk.vtkCommand.LeftButtonPressEvent, vtk.vtkCommand.LeftButtonReleaseEvent, vtk.vtkCommand.MouseMoveEvent]:
      tag = self._interactor.AddObserver(e, self._processEvent, 1.0)
      self._interactorObserverTags.append(tag)

  def disable(self):
    """ Disables WindowLevelEffect for the slice widget specified during initialization """
    for tag in self._interactorObserverTags:
      self._interactor.RemoveObserver(tag)
    self._interactorObserverTags = []

  def _createWLCursor(self):
    iconPath = os.path.join(os.path.dirname(sys.modules[self.__module__].__file__),
                            '../Resources/Icons/icon-cursor-WindowLevel.png')
    pixmap = qt.QPixmap(iconPath)
    return qt.QCursor(qt.QIcon(pixmap).pixmap(32, 32), 0, 0)

  def _processEvent(self, caller=None, event=None):
    """ handle events from the render window interactor """
    bgLayer = self._sliceLogic.GetBackgroundLayer()
    fgLayer = self._sliceLogic.GetForegroundLayer()

    bgNode = bgLayer.GetVolumeNode()
    fgNode = fgLayer.GetVolumeNode()

    changeFg = 1 if fgNode and self._compositeNode.GetForegroundOpacity() > 0.5 else 0
    changeBg = not changeFg

    if event == "LeftButtonPressEvent":
      self.__actionState = "dragging"
      self._sliceWidget.setCursor(self.__cursor)

      xy = self._interactor.GetEventPosition()
      self.__startXYPosition = xy
      self.__currentXYPosition = xy

      if bgNode:
        bgDisplay = bgNode.GetDisplayNode()
        self._bgStartWindowLevel = [bgDisplay.GetWindow(), bgDisplay.GetLevel()]
      if fgNode:
        fgDisplay = fgNode.GetDisplayNode()
        self._fgStartWindowLevel = [fgDisplay.GetWindow(), fgDisplay.GetLevel()]
      self._abortEvent(event)

    elif event == "MouseMoveEvent":
      if self.__actionState == "dragging":
        if bgNode and changeBg:
          self._updateNodeWL(bgNode, self._bgStartWindowLevel, self.__startXYPosition)
        if fgNode and changeFg:
          self._updateNodeWL(fgNode, self._fgStartWindowLevel, self.__startXYPosition)
        self._abortEvent(event)

    elif event == "LeftButtonReleaseEvent":
      self._sliceWidget.unsetCursor()
      self.__actionState = ""
      self._abortEvent(event)

  def _updateNodeWL(self, node, startWindowLevel, startXY):

    currentXY = self._interactor.GetEventPosition()

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
    """Set the AbortFlag on the vtkCommand associated with the event - causes other things listening to the
    interactor not to receive the events"""
    # TODO: make interactorObserverTags a map to we can
    # explicitly abort just the event we handled - it will
    # be slightly more efficient
    for tag in self._interactorObserverTags:
      cmd = self._interactor.GetCommand(tag)
      cmd.SetAbortFlag(1)