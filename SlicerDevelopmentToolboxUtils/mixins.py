import qt, vtk, ctk
import os, logging
import slicer
import SimpleITK as sitk
import sitkUtils
from packaging import version
import dicom


class ParameterNodeObservationMixin(object):
  """
  This class can be used as a mixin for all classes that provide a method getParameterNode like
  ScriptedLoadableModuleLogic. ParameterNodeObservationMixin provides the possibility to simply
  observe the parameter node. Custom events can be observed and from your ScriptedLoadableModuleLogic
  invoked. Originated was this class from slicer.util.VTKObservationMixin
  """

  def __del__(self):
    self.removeEventObservers()

  @property
  def parameterNode(self):
    try:
      return self._parameterNode
    except AttributeError:
      self._parameterNode = self.getParameterNode() if hasattr(self, "getParameterNode") else self._createParameterNode()
    return self._parameterNode

  @property
  def parameterNodeObservers(self):
    try:
      return self._parameterNodeObservers
    except AttributeError:
      self._parameterNodeObservers = []
    return self._parameterNodeObservers

  def _createParameterNode(self):
    parameterNode = slicer.vtkMRMLScriptedModuleNode()
    slicer.mrmlScene.AddNode(parameterNode)
    return parameterNode

  def removeEventObservers(self, method=None):
    for e, m, g, t in list(self.parameterNodeObservers):
      if method == m or method is None:
        self.parameterNode.RemoveObserver(t)
        self.parameterNodeObservers.remove([e, m, g, t])

  def addEventObserver(self, event, method, group='none'):
    if self.hasEventObserver(event, method):
      self.removeEventObserver(event, method)
    tag = self.parameterNode.AddObserver(event, method)
    self.parameterNodeObservers.append([event, method, group, tag])

  def removeEventObserver(self, event, method):
    for e, m, g, t in self.parameterNodeObservers:
      if e == event and m == method:
        self.parameterNode.RemoveObserver(t)
        self.parameterNodeObservers.remove([e, m, g, t])

  def hasEventObserver(self, event, method):
    for e, m, g, t in self.parameterNodeObservers:
      if e == event and m == method:
        return True
    return False

  def invokeEvent(self, event, callData=None):
    if callData:
      self.parameterNode.InvokeEvent(event, callData)
    else:
      self.parameterNode.InvokeEvent(event)

  def getEventObservers(self):
    observerMethodDict = {}
    for e, m, g, t in self.parameterNodeObservers:
      observerMethodDict[e] = m
    return observerMethodDict


class GeneralModuleMixin(ParameterNodeObservationMixin):

  def _processKwargs(self, **kwargs):
    for key, value in iter(kwargs.items()):
      if hasattr(self, key):
        setattr(self, key, value)

  @staticmethod
  def getSlicerErrorLogPath():
    return slicer.app.errorLogModel().filePath

  @staticmethod
  def getTime():
    import datetime
    d = datetime.datetime.now()
    return d.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-4] + "Z"

  def hasSetting(self, setting, moduleName=None):
    moduleName = moduleName if moduleName else self.moduleName
    settings = qt.QSettings()
    return settings.contains(moduleName + '/' + setting)

  def getSetting(self, setting, moduleName=None, default=None):
    moduleName = moduleName if moduleName else self.moduleName
    settings = qt.QSettings()
    setting = settings.value(moduleName + '/' + setting)
    return setting if setting is not None else default

  def setSetting(self, setting, value, moduleName=None):
    moduleName = moduleName if moduleName else self.moduleName
    settings = qt.QSettings()
    settings.setValue(moduleName + '/' + setting, value)

  def removeSetting(self, setting, moduleName=None):
    moduleName = moduleName if moduleName else self.moduleName
    settings = qt.QSettings()
    settings.remove(moduleName+ '/' + setting)

  @staticmethod
  def createTimer(interval, slot, singleShot=False):
    timer = qt.QTimer()
    timer.setInterval(interval)
    timer.timeout.connect(slot)
    timer.setSingleShot(singleShot)
    return timer


class UICreationHelpers(object):

  @staticmethod
  def createSliderWidget(minimum, maximum):
    slider = slicer.qMRMLSliderWidget()
    slider.minimum = minimum
    slider.maximum = maximum
    return slider

  @staticmethod
  def createLabel(title, **kwargs):
    label = qt.QLabel(title)
    return UICreationHelpers.extendQtGuiElementProperties(label, **kwargs)

  @staticmethod
  def createLineEdit(title, **kwargs):
    lineEdit = qt.QLineEdit(title)
    return UICreationHelpers.extendQtGuiElementProperties(lineEdit, **kwargs)

  @staticmethod
  def createButton(title, buttonClass=qt.QPushButton, **kwargs):
    button = buttonClass(title)
    button.setCursor(qt.Qt.PointingHandCursor)
    return UICreationHelpers.extendQtGuiElementProperties(button, **kwargs)

  @staticmethod
  def createRadioButton(text, **kwargs):
    button = qt.QRadioButton(text)
    button.setCursor(qt.Qt.PointingHandCursor)
    return UICreationHelpers.extendQtGuiElementProperties(button, **kwargs)

  @staticmethod
  def createDirectoryButton(**kwargs):
    button = ctk.ctkDirectoryButton()
    for key, value in iter(kwargs.items()):
      if hasattr(button, key):
        setattr(button, key, value)
    return button

  @staticmethod
  def extendQtGuiElementProperties(element, **kwargs):
    for key, value in iter(kwargs.items()):
      if hasattr(element, key):
        setattr(element, key, value)
      else:
        if key == "fixedHeight":
          element.minimumHeight = value
          element.maximumHeight = value
        elif key == 'hidden':
          if value:
            element.hide()
          else:
            element.show()
        else:
          logging.error("%s does not have attribute %s" % (element.className(), key))
    return element

  @staticmethod
  def createComboBox(**kwargs):
    combobox = slicer.qMRMLNodeComboBox()
    combobox.addEnabled = False
    combobox.removeEnabled = False
    combobox.noneEnabled = True
    combobox.showHidden = False
    for key, value in iter(kwargs.items()):
      if hasattr(combobox, key):
        setattr(combobox, key, value)
      else:
        logging.error("qMRMLNodeComboBox does not have attribute %s" % key)
    combobox.setMRMLScene(slicer.mrmlScene)
    return combobox

  @staticmethod
  def createProgressDialog(parent=None, value=0, maximum=100, labelText="", windowTitle="Processing...",
                           windowFlags=None, **kwargs):
    """Display a modal QProgressDialog. Go to QProgressDialog documentation
    http://pyqt.sourceforge.net/Docs/PyQt4/qprogressdialog.html for more keyword arguments, that could be used.
    E.g. progressbar = createProgressIndicator(autoClose=False) if you don't want the progress dialog to automatically
    close.
    Updating progress value with progressbar.value = 50
    Updating label text with progressbar.labelText = "processing XYZ"
    """
    progressIndicator = qt.QProgressDialog(parent if parent else slicer.util.mainWindow(),
                                           windowFlags if windowFlags else qt.Qt.WindowStaysOnTopHint)
    progressIndicator.minimumDuration = 0
    progressIndicator.maximum = maximum
    progressIndicator.value = value
    progressIndicator.windowTitle = windowTitle
    progressIndicator.labelText = labelText
    for key, value in iter(kwargs.items()):
      if hasattr(progressIndicator, key):
        setattr(progressIndicator, key, value)
    return progressIndicator

  @staticmethod
  def createHLayout(elements, **kwargs):
    return UICreationHelpers.createLayout(qt.QHBoxLayout, elements, **kwargs)

  @staticmethod
  def createVLayout(elements, **kwargs):
    return UICreationHelpers.createLayout(qt.QVBoxLayout, elements, **kwargs)

  @staticmethod
  def createLayout(layoutClass, elements, **kwargs):
    widget = qt.QWidget()
    rowLayout = layoutClass()
    widget.setLayout(rowLayout)
    for element in elements:
      rowLayout.addWidget(element)
    for key, value in iter(kwargs.items()):
      if hasattr(rowLayout, key):
        setattr(rowLayout, key, value)
    return widget

  @staticmethod
  def createListView(name, headerLabels):
    view = qt.QListView()
    view.setObjectName(name)
    view.setSpacing(3)
    model = qt.QStandardItemModel()
    model.setHorizontalHeaderLabels(headerLabels)
    view.setModel(model)
    view.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
    return view, model


class ModuleWidgetMixin(GeneralModuleMixin, UICreationHelpers):

  @property
  def layoutManager(self):
    return slicer.app.layoutManager()

  def createSliceWidgetClassMembers(self, name):
    widget = self.layoutManager.sliceWidget(name)
    if not widget:
      raise ValueError("sliceWidget name %s does not exist." % name)
    self._addWidget(widget, name)
    self._addCompositeNode(widget.mrmlSliceCompositeNode(), name)
    self._addSliceView(widget.sliceView(), name)
    self._addSliceViewInteractor(widget.sliceView().interactorStyle().GetInteractor(), name)
    self._addSliceLogic(widget.sliceLogic(), name)
    self._addSliceNode(widget.sliceLogic().GetSliceNode(), name)

  def _addWidget(self, widget, name):
    setattr(self, name.lower()+"Widget", widget)
    self._widgets = getattr(self, "_widgets", [])
    if not widget in self._widgets:
      self._widgets.append(widget)

  def _addCompositeNode(self, compositeNode, name):
    setattr(self, name.lower()+"CompositeNode", compositeNode)
    self._compositeNodes = getattr(self, "_compositeNodes", [])
    if not compositeNode in self._compositeNodes:
      self._compositeNodes.append(compositeNode)

  def _addSliceView(self, sliceView, name):
    setattr(self, name.lower()+"SliceView", sliceView)
    self._sliceViews = getattr(self, "_sliceViews", [])
    if not sliceView in self._sliceViews:
      self._sliceViews.append(sliceView)

  def _addSliceViewInteractor(self, sliceViewInteractor, name):
    setattr(self, name.lower()+"SliceViewInteractor", sliceViewInteractor)
    self._sliceViewInteractors = getattr(self, "_sliceViewInteractors", [])
    if not sliceViewInteractor in self._sliceViewInteractors:
      self._sliceViewInteractors.append(sliceViewInteractor)

  def _addSliceLogic(self, sliceLogic, name):
    setattr(self, name.lower()+"SliceLogic", sliceLogic)
    self._sliceLogics = getattr(self, "_sliceLogics", [])
    if not sliceLogic in self._sliceLogics:
      self._sliceLogics.append(sliceLogic)

  def _addSliceNode(self, sliceNode, name):
    setattr(self, name.lower()+"SliceNode", sliceNode)
    self._sliceNodes = getattr(self, "_sliceNodes", [])
    if not sliceNode in self._sliceNodes:
      self._sliceNodes.append(sliceNode)

  @staticmethod
  def getAllVisibleWidgets():
    lm = slicer.app.layoutManager()
    sliceLogics = lm.mrmlSliceLogics()
    for n in range(sliceLogics.GetNumberOfItems()):
      sliceLogic = sliceLogics.GetItemAsObject(n)
      widget = lm.sliceWidget(sliceLogic.GetName())
      if widget.sliceView().visible:
         yield widget

  @staticmethod
  def linkAllSliceWidgets(link):
    for widget in ModuleWidgetMixin.getAllVisibleWidgets():
      compositeNode = widget.mrmlSliceCompositeNode()
      compositeNode.SetLinkedControl(link)
      compositeNode.SetInteractionFlagsModifier(4+8+16)

  @staticmethod
  def hideAllLabels():
    for widget in ModuleWidgetMixin.getAllVisibleWidgets():
      compositeNode = widget.mrmlSliceCompositeNode()
      compositeNode.SetLabelOpacity(0)

  @staticmethod
  def setFiducialNodeVisibility(targetNode, show=True):
    markupsLogic = slicer.modules.markups.logic()
    markupsLogic.SetAllMarkupsVisibility(targetNode, show)

  @staticmethod
  def hideAllFiducialNodes():
    for targetNode in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"):
      ModuleWidgetMixin.setFiducialNodeVisibility(targetNode, show=False)

  @staticmethod
  def setFOV(sliceLogic, FOV):
    sliceNode = sliceLogic.GetSliceNode()
    sliceNode.SetFieldOfView(FOV[0], FOV[1], FOV[2])
    sliceNode.UpdateMatrices()

  @staticmethod
  def removeNodeFromMRMLScene(node):
    if node:
      slicer.mrmlScene.RemoveNode(node)
      node = None

  @staticmethod
  def xyToRAS(sliceLogic, xyPoint):
    sliceNode = sliceLogic.GetSliceNode()
    rast = sliceNode.GetXYToRAS().MultiplyPoint(xyPoint + (0,1,))
    return rast[:3]

  @staticmethod
  def refreshViewNodeIDs(node, sliceNodes):
    displayNode = node.GetDisplayNode()
    if displayNode:
      displayNode.RemoveAllViewNodeIDs()
      for sliceNode in sliceNodes:
        displayNode.AddViewNodeID(sliceNode.GetID())

  @staticmethod
  def removeViewNodeIDs(node, sliceNodes):
    displayNode = node.GetDisplayNode()
    if displayNode:
      displayNode.RemoveAllViewNodeIDs()
      for sliceNode in sliceNodes:
        displayNode.RemoveViewNodeID(sliceNode.GetID())

  @staticmethod
  def jumpSliceNodeToTarget(sliceNode, targetNode, index):
    point = [0,0,0,0]
    targetNode.GetMarkupPointWorld(index, 0, point)
    sliceNode.JumpSlice(point[0], point[1], point[2])

  @staticmethod
  def resetToRegularViewMode():
    interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
    interactionNode.SwitchToViewTransformMode()
    interactionNode.SetPlaceModePersistence(0)

  @staticmethod
  def confirmOrSaveDialog(message, title='mpReview'):
    box = qt.QMessageBox(qt.QMessageBox.Question, title, message)
    box.addButton("Exit, discard changes", qt.QMessageBox.AcceptRole)
    box.addButton("Save changes", qt.QMessageBox.ActionRole)
    box.addButton("Cancel", qt.QMessageBox.RejectRole)
    return box.exec_()

  def updateProgressBar(self, **kwargs):
    progress = kwargs.pop('progress', None)
    assert progress, "Keyword argument progress (instance of QProgressDialog) is missing"
    for key, value in iter(kwargs.items()):
      if hasattr(progress, key):
        setattr(progress, key, value)
      else:
        print("key %s not found" % key)
    slicer.app.processEvents()

  @staticmethod
  def setBackgroundToVolumeID(volume, clearLabels=True, showLabelOutline=False, sliceWidgets=None):
    if not sliceWidgets:
      sliceWidgets = ModuleWidgetMixin.getAllVisibleWidgets()
    for widget in sliceWidgets:
      compositeNode = widget.mrmlSliceCompositeNode()
      if clearLabels:
        compositeNode.SetLabelVolumeID(None)
      compositeNode.SetForegroundVolumeID(None)
      compositeNode.SetBackgroundVolumeID(volume.GetID() if volume else None)
      sliceNode = widget.sliceLogic().GetSliceNode()
      sliceNode.RotateToVolumePlane(volume)
      sliceNode.SetUseLabelOutline(showLabelOutline)

  def createIcon(self, filename, iconPath=None):
    if not iconPath:
      iconPath = os.path.join(self.modulePath, 'Resources/Icons')
    path = os.path.join(iconPath, filename)
    pixmap = qt.QPixmap(path)
    return qt.QIcon(pixmap)

  @staticmethod
  def createAndGetRawColoredPixelMap(color, width=24, height=24, drawBorder=True):
    pixmap = qt.QPixmap(width, height)
    pixmap.fill(qt.QColor(color))
    if drawBorder:
      ModuleWidgetMixin.drawBorder(pixmap)
    return ModuleWidgetMixin.pixelmapAsRaw(pixmap)

  @staticmethod
  def drawBorder(pixmap):
    painter = qt.QPainter(pixmap)
    rect = pixmap.rect()
    tl = rect.topLeft()
    tr = rect.topRight()
    bl = rect.bottomLeft()
    br = rect.bottomRight()
    for start, end in [[tl, tr],[tr, br],[br, bl],[bl, tl]]:
      painter.drawLine(start, end)

  @staticmethod
  def pixelmapAsRaw(pixmap):
    byteArray = qt.QByteArray()
    buffer = qt.QBuffer(byteArray)
    pixmap.save(buffer, "PNG")
    return "data:image/png;base64," + byteArray.toBase64().data()

  def showMainAppToolbars(self, show=True):
    w = slicer.util.mainWindow()
    for c in w.children():
      if str(type(c)).find('ToolBar')>0:
        if show:
          c.show()
        else:
          c.hide()

  def _getMinimumTextWidth(self, text):
    fm = qt.QFontMetrics(qt.QFont(text, 0))
    width = fm.width(text)
    return width

  def hideAllSegmentations(self):
    for segmentation in slicer.util.getNodesByClass('vtkMRMLSegmentationNode'):
      segmentation.SetDisplayVisibility(False)

  @staticmethod
  def isQtVersionOlder(than="5.0.0"):
    return version.parse(qt.Qt.qVersion()) < version.parse(than)


class ModuleLogicMixin(GeneralModuleMixin):

  @property
  def scalarVolumePlugin(self):
    return slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()

  @property
  def volumesLogic(self):
    return slicer.modules.volumes.logic()

  @property
  def markupsLogic(self):
    return slicer.modules.markups.logic()

  @property
  def cropVolumeLogic(self):
    return slicer.modules.cropvolume.logic()

  @staticmethod
  def truncatePath(path):
    try:
      split = path.split('/')
      path = '.../' + split[-2] + '/' + split[-1]
    except (IndexError, AttributeError):
      pass
    return path

  @staticmethod
  def cloneFiducials(original, cloneName, keepDisplayNode=False):
    clone = slicer.vtkMRMLMarkupsFiducialNode()
    clone.Copy(original)
    clone.SetName(cloneName)
    slicer.mrmlScene.AddNode(clone)
    if not keepDisplayNode:
      displayNode = slicer.vtkMRMLMarkupsDisplayNode()
      slicer.mrmlScene.AddNode(displayNode)
      clone.SetAndObserveDisplayNodeID(displayNode.GetID())
    return clone

  @staticmethod
  def getMostRecentFile(path, fileType, filter=None):
    assert type(fileType) is str
    files = [f for f in os.listdir(path) if f.endswith(fileType)]
    if len(files) == 0:
      return None
    mostRecent = None
    storedTimeStamp = 0
    for filename in files:
      if filter and not filter in filename:
        continue
      actualFileName = filename.split(".")[0]
      timeStamp = int(actualFileName.split("-")[-1])
      if timeStamp > storedTimeStamp:
        mostRecent = filename
        storedTimeStamp = timeStamp
    return mostRecent

  @staticmethod
  def getTargetPosition(targetNode, index):
    position = [0.0, 0.0, 0.0]
    targetNode.GetNthFiducialPosition(index, position)
    return position

  @staticmethod
  def get3DDistance(p1, p2):
    return [abs(p1[0]-p2[0]), abs(p1[1]-p2[1]), abs(p1[2]-p2[2])]

  @staticmethod
  def get3DEuclideanDistance(pos1, pos2):
    rulerNode = slicer.vtkMRMLAnnotationRulerNode()
    rulerNode.SetPosition1(pos1)
    rulerNode.SetPosition2(pos2)
    distance3D = rulerNode.GetDistanceMeasurement()
    return distance3D

  @staticmethod
  def dilateMask(label, dilateValue=1.0, erodeValue=0.0, marginSize=5.0):
    imagedata = label.GetImageData()
    dilateErode = vtk.vtkImageDilateErode3D()
    dilateErode.SetInputData(imagedata)
    dilateErode.SetDilateValue(dilateValue)
    dilateErode.SetErodeValue(erodeValue)
    spacing = label.GetSpacing()
    kernelSizePixel = [int(round((abs(marginSize) / spacing[componentIndex]+1)/2)*2-1) for componentIndex in range(3)]
    dilateErode.SetKernelSize(kernelSizePixel[0], kernelSizePixel[1], kernelSizePixel[2])
    dilateErode.Update()
    label.SetAndObserveImageData(dilateErode.GetOutput())

  @staticmethod
  def getCentroidForLabel(labelNode, value):
    if not labelNode:
      return None
    labelAddress = sitkUtils.GetSlicerITKReadWriteAddress(labelNode.GetName())
    labelImage = sitk.ReadImage(labelAddress)

    ls = sitk.LabelStatisticsImageFilter()
    ls.Execute(labelImage, labelImage)
    bb = ls.GetBoundingBox(value)

    centroid = None # sagittal, coronal, axial
    if len(bb) > 0:
      centerIJK = [((bb[0] + bb[1]) / 2), ((bb[2] + bb[3]) / 2), ((bb[4] + bb[5]) / 2)]
      logging.debug('BB is: ' + str(bb))
      logging.debug('i_center = '+str(centerIJK[0]))
      logging.debug('j_center = '+str(centerIJK[1]))
      logging.debug('k_center = '+str(centerIJK[2]))

      IJKtoRAS = vtk.vtkMatrix4x4()
      labelNode.GetIJKToRASMatrix(IJKtoRAS)
      IJKtoRASDir = vtk.vtkMatrix4x4()
      labelNode.GetIJKToRASDirectionMatrix(IJKtoRASDir)
      RAScoord = IJKtoRAS.MultiplyPoint((centerIJK[0], centerIJK[1], centerIJK[2], 1))

      order = labelNode.ComputeScanOrderFromIJKToRAS(IJKtoRAS)
      if order == 'IS':
        RASDir = IJKtoRASDir.MultiplyPoint((RAScoord[0], RAScoord[1], RAScoord[2], 1))
        centroid = [-RASDir[0], -RASDir[1], RASDir[2]]
      elif order == 'AP':
        RASDir = IJKtoRASDir.MultiplyPoint((RAScoord[0], RAScoord[1], RAScoord[2], 1))
        centroid = [-RASDir[0], -RASDir[2], -RASDir[1]]
      elif order == 'LR':
        RASDir = IJKtoRASDir.MultiplyPoint((RAScoord[2], RAScoord[1], RAScoord[0], 1))
        centroid = [RASDir[0], -RASDir[2], -RASDir[1]]
    return centroid

  @staticmethod
  def roundInt(value, exceptionReturnValue=0):
    try:
      return int(round(value))
    except ValueError:
      return exceptionReturnValue

  @staticmethod
  def getIJKForXYZ(sliceWidget, p):
    xyz = sliceWidget.sliceView().convertRASToXYZ(p)
    layerLogic = sliceWidget.sliceLogic().GetBackgroundLayer()
    xyToIJK = layerLogic.GetXYToIJKTransform()
    ijkFloat = xyToIJK.TransformDoublePoint(xyz)
    ijk = [ModuleLogicMixin.roundInt(value) for value in ijkFloat]
    return ijk

  @staticmethod
  def createCroppedVolume(inputVolume, roi):
    cropVolumeLogic = slicer.modules.cropvolume.logic()
    cropVolumeParameterNode = slicer.vtkMRMLCropVolumeParametersNode()
    cropVolumeParameterNode.SetROINodeID(roi.GetID())
    cropVolumeParameterNode.SetInputVolumeNodeID(inputVolume.GetID())
    cropVolumeParameterNode.SetVoxelBased(True)
    cropVolumeLogic.Apply(cropVolumeParameterNode)
    croppedVolume = slicer.mrmlScene.GetNodeByID(cropVolumeParameterNode.GetOutputVolumeNodeID())
    return croppedVolume

  @staticmethod
  def createMaskedVolume(inputVolume, labelVolume, outputVolumeName=None):
    maskedVolume = slicer.vtkMRMLScalarVolumeNode()
    if outputVolumeName:
      maskedVolume.SetName(outputVolumeName)
    slicer.mrmlScene.AddNode(maskedVolume)
    params = {'InputVolume': inputVolume, 'MaskVolume': labelVolume, 'OutputVolume': maskedVolume}
    slicer.cli.run(slicer.modules.maskscalarvolume, None, params, wait_for_completion=True)
    return maskedVolume

  @staticmethod
  def createVTKTubeFilter(startPoint, endPoint, radius, numSides):
    lineSource = vtk.vtkLineSource()
    lineSource.SetPoint1(startPoint)
    lineSource.SetPoint2(endPoint)

    tubeFilter = vtk.vtkTubeFilter()
    tubeFilter.SetInputConnection(lineSource.GetOutputPort())
    tubeFilter.SetRadius(radius)
    tubeFilter.SetNumberOfSides(numSides)
    tubeFilter.CappingOn()
    tubeFilter.Update()
    return tubeFilter

  @staticmethod
  def createLabelMapFromCroppedVolume(volume, name, lowerThreshold=0, upperThreshold=2000, labelValue=1):
    volumesLogic = slicer.modules.volumes.logic()
    labelVolume = volumesLogic.CreateAndAddLabelVolume(volume, name)
    imageData = labelVolume.GetImageData()
    imageThreshold = vtk.vtkImageThreshold()
    imageThreshold.SetInputData(imageData)
    imageThreshold.ThresholdBetween(lowerThreshold, upperThreshold)
    imageThreshold.SetInValue(labelValue)
    imageThreshold.Update()
    labelVolume.SetAndObserveImageData(imageThreshold.GetOutput())
    return labelVolume

  @staticmethod
  def getIslandCount(image, index):
    imageSize = image.GetSize()
    index = [0, 0, index]
    extractor = sitk.ExtractImageFilter()
    extractor.SetSize([imageSize[0], imageSize[1], 0])
    extractor.SetIndex(index)
    slice = extractor.Execute(image)
    cc = sitk.ConnectedComponentImageFilter()
    cc.Execute(slice)
    return cc.GetObjectCount()

  @staticmethod
  def applyOtsuFilter(volume):
    outputVolume = slicer.vtkMRMLScalarVolumeNode()
    outputVolume.SetName('ZFrame_Otsu_Output')
    slicer.mrmlScene.AddNode(outputVolume)
    params = {'inputVolume': volume.GetID(),
              'outputVolume': outputVolume.GetID(),
              'insideValue': 0, 'outsideValue': 1}

    slicer.cli.run(slicer.modules.otsuthresholdimagefilter, None, params, wait_for_completion=True)
    return outputVolume

  @staticmethod
  def getDirectorySize(directory):
    size = 0
    for path, dirs, files in os.walk(directory):
      for currentFile in files:
        if not ".DS_Store" in currentFile:
          size += os.path.getsize(os.path.join(path, currentFile))
    return size

  @staticmethod
  def createDirectory(directory, message=None):
    if message:
      logging.debug(message)
    try:
      os.makedirs(directory)
    except OSError:
      logging.debug('Failed to create the following directory: ' + directory)

  @staticmethod
  def findElement(dom, name):
    for e in [e for e in dom.getElementsByTagName('element') if e.getAttribute('name') == name]:
      try:
        return e.childNodes[0].nodeValue
      except IndexError:
        return ""

  @staticmethod
  def getDICOMValue(inputArg, tagName, default=""):
    try:
      if type(inputArg) is dicom.dataset.FileDataset:
        value = getattr(inputArg, tagName)
      elif type(inputArg) is str and os.path.isfile(inputArg):
        value = slicer.dicomDatabase.fileValue(inputArg, tagName)
      elif type(inputArg) is slicer.vtkMRMLScalarVolumeNode:
        f = inputArg.GetStorageNode().GetFileName()
        value = slicer.dicomDatabase.fileValue(f, tagName)
      elif type(inputArg) is slicer.vtkMRMLMultiVolumeNode:
        f = slicer.dicomDatabase.fileForInstance(inputArg.GetAttribute("DICOM.instanceUIDs").split(" ")[0])
        value = slicer.dicomDatabase.fileValue(f, tagName)
      else:
        logging.warning("Could not retrieve DICOM tag value from input parameter %s" % inputArg)
        value = default
    except Exception as exc:
      logging.error(exc)
      value = default
    return value

  @staticmethod
  def getFileList(directory):
    return [f for f in os.listdir(directory) if ".DS_Store" not in f]

  @staticmethod
  def importStudy(dicomDataDir):
    indexer = ctk.ctkDICOMIndexer()
    indexer.addDirectory(slicer.dicomDatabase, dicomDataDir)
    indexer.waitForImportFinished()

  @staticmethod
  def createScalarVolumeNode(name=None):
    return ModuleLogicMixin.createNode(slicer.vtkMRMLScalarVolumeNode, name=name)

  @staticmethod
  def createBSplineTransformNode(name=None):
    return ModuleLogicMixin.createNode(slicer.vtkMRMLBSplineTransformNode, name=name)

  @staticmethod
  def createLinearTransformNode(name=None):
    return ModuleLogicMixin.createNode(slicer.vtkMRMLLinearTransformNode, name=name)

  @staticmethod
  def createModelNode(name=None):
    return ModuleLogicMixin.createNode(slicer.vtkMRMLModelNode, name=name)

  @staticmethod
  def createNode(nodeType, name=None):
    node = nodeType()
    if name:
      node.SetName(name)
    slicer.mrmlScene.AddNode(node)
    return node

  @staticmethod
  def saveNodeData(node, outputDir, extension, replaceUnwantedCharacters=True, name=None, overwrite=True):
    name = name if name else node.GetName()
    if replaceUnwantedCharacters:
      name = ModuleLogicMixin.replaceUnwantedCharacters(name)
    filename = os.path.join(outputDir, name + extension)
    if os.path.exists(filename) and not overwrite:
      return True, name
    return slicer.util.saveNode(node, filename), name

  @staticmethod
  def replaceUnwantedCharacters(string, characters=None, replaceWith="-"):
    if not characters:
      characters = [": ", " ", ":", "/"]
    for character in characters:
      string = string.replace(character, replaceWith)
    return string

  @staticmethod
  def handleSaveNodeDataReturn(success, name, successfulList, failedList):
    listToAdd = successfulList if success else failedList
    listToAdd.append(name)

  @staticmethod
  def applyTransform(transform, node):
    tfmLogic = slicer.modules.transforms.logic()
    node.SetAndObserveTransformNodeID(transform.GetID())
    tfmLogic.hardenTransform(node)

  @staticmethod
  def createAndObserveDisplayNode(node, displayNodeClass=slicer.vtkMRMLDisplayNode):
    displayNode = displayNodeClass()
    slicer.mrmlScene.AddNode(displayNode)
    node.SetAndObserveDisplayNodeID(displayNode.GetID())
    return displayNode

  @staticmethod
  def setNodeVisibility(node, visible):
    displayNode = node.GetDisplayNode()
    if displayNode is not None:
      displayNode.SetVisibility(visible)

  @staticmethod
  def setNodeSliceIntersectionVisibility(node, visible):
    displayNode = node.GetDisplayNode()
    if displayNode is not None:
      displayNode.SetSliceIntersectionVisibility(visible)

  @staticmethod
  def isVolumeExtentValid(volume):
    imageData = volume.GetImageData()
    try:
      extent = imageData.GetExtent()
      return extent[1] > 0 and extent[3] > 0 and extent[5] > 0
    except AttributeError:
      return False

  @staticmethod
  def isAnyListItemInString(string, listItem):
    return any(item in string for item in listItem)

  @staticmethod
  def getReferencedVolumeFromSegmentationNode(segmentationNode):
    if not segmentationNode:
      return None
    return segmentationNode.GetNodeReference(segmentationNode.GetReferenceImageGeometryReferenceRole())

  @staticmethod
  def runBRAINSResample(inputVolume, referenceVolume, outputVolume, warpTransform=None):
    params = {'inputVolume': inputVolume, 'referenceVolume': referenceVolume, 'outputVolume': outputVolume,
              'interpolationMode': 'NearestNeighbor', 'pixelType':'short'}
    if warpTransform:
      params['warpTransform'] = warpTransform

    logging.debug('About to run BRAINSResample CLI with those params: %s' % params)
    slicer.cli.run(slicer.modules.brainsresample, None, params, wait_for_completion=True)
    slicer.mrmlScene.AddNode(outputVolume)
