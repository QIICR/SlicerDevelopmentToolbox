import datetime
import xml.dom

import qt
import slicer
import vtk
import os
import sys
import ctk

from constants import DICOMTAGS
from events import SlicerDevelopmentToolboxEvents
from helpers import SmartDICOMReceiver, DICOMDirectorySender
from mixins import ModuleWidgetMixin, ModuleLogicMixin
from decorators import singleton


@singleton
class CustomStatusProgressbar(qt.QWidget):

  STYLE = "QWidget{background-color:#FFFFFF;}"

  @property
  def text(self):
    return self.textLabel.text

  @text.setter
  def text(self, value):
    self.textLabel.text = value

  @property
  def value(self):
    return self.progress.value

  @value.setter
  def value(self, value):
    self.progress.value = value
    self.refreshProgressVisibility()

  @property
  def maximum(self):
    return self.progress.maximum

  @maximum.setter
  def maximum(self, value):
    self.progress.maximum = value
    self.refreshProgressVisibility()

  def __init__(self, parent=None, **kwargs):
    qt.QWidget.__init__(self, parent, **kwargs)
    self.setup()

  def setup(self):
    self.textLabel = qt.QLabel()
    self.progress = qt.QProgressBar()
    self.maximumHeight = slicer.util.mainWindow().statusBar().height
    rowLayout = qt.QHBoxLayout()
    self.setLayout(rowLayout)
    rowLayout.addWidget(self.textLabel, 1)
    rowLayout.addWidget(self.progress, 1)
    self.setStyleSheet(self.STYLE)
    self.refreshProgressVisibility()
    slicer.util.mainWindow().statusBar().addWidget(self, 1)

  def updateStatus(self, text, value=None):
    self.text = text
    if value is not None:
      self.value = value

  def reset(self):
    self.text = ""
    self.progress.reset()
    self.progress.maximum = 100
    self.refreshProgressVisibility()

  def refreshProgressVisibility(self):
    self.progress.visible = self.value > 0 and self.progress.maximum > 0 or self.progress.maximum == 0


class TargetCreationWidget(qt.QWidget, ModuleWidgetMixin):

  HEADERS = ["Name","Delete"]
  MODIFIED_EVENT = "ModifiedEvent"
  FIDUCIAL_LIST_OBSERVED_EVENTS = [MODIFIED_EVENT]

  DEFAULT_FIDUCIAL_LIST_NAME = None
  DEFAULT_CREATE_FIDUCIALS_TEXT = "Place Target(s)"
  DEFAULT_MODIFY_FIDUCIALS_TEXT = "Modify Target(s)"

  TargetingStartedEvent = vtk.vtkCommand.UserEvent + 335
  TargetingFinishedEvent = vtk.vtkCommand.UserEvent + 336

  ICON_SIZE = qt.QSize(24, 24)

  @property
  def currentNode(self):
    return self.fiducialListSelector.currentNode()

  @currentNode.setter
  def currentNode(self, node):
    if self._currentNode:
      self.removeTargetListObservers()
    self.fiducialListSelector.setCurrentNode(node)
    self._currentNode = node
    if node:
      self.addTargetListObservers()
      self.selectionNode.SetReferenceActivePlaceNodeID(node.GetID())
    else:
      self.selectionNode.SetReferenceActivePlaceNodeID(None)

    self.updateButtons()
    self.updateTable()

  @property
  def targetListSelectorVisible(self):
    return self.targetListSelectorArea.visible

  @targetListSelectorVisible.setter
  def targetListSelectorVisible(self, visible):
    self.targetListSelectorArea.visible = visible

  def __init__(self, parent=None, **kwargs):
    qt.QWidget.__init__(self, parent)
    self.iconPath = os.path.join(os.path.dirname(sys.modules[self.__module__].__file__), '../Resources/Icons')
    self.processKwargs(**kwargs)
    self.connectedButtons = []
    self.fiducialNodeObservers = []
    self.selectionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSelectionNodeSingleton")
    self.interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
    self.setupIcons()
    self.setup()
    self._currentNode = None
    self.setupConnections()

  def processKwargs(self, **kwargs):
    for key, value in kwargs.iteritems():
      if hasattr(self, key):
        setattr(self, key, value)

  def reset(self):
    self.stopPlacing()
    self.currentNode = None

  def setupIcons(self):
    self.setTargetsIcon = self.createIcon("icon-addFiducial.png", self.iconPath)
    self.modifyTargetsIcon = self.createIcon("icon-modifyFiducial.png", self.iconPath)
    self.finishIcon = self.createIcon("icon-apply.png", self.iconPath)

  def setup(self):
    self.setLayout(qt.QGridLayout())
    self.setupTargetFiducialListSelector()
    self.setupTargetTable()
    self.setupButtons()

  def setupTargetFiducialListSelector(self):
    self.fiducialListSelector = self.createComboBox(nodeTypes=["vtkMRMLMarkupsFiducialNode", ""], addEnabled=True,
                                                    removeEnabled=True, noneEnabled=True, showChildNodeTypes=False,
                                                    selectNodeUponCreation=True, toolTip="Select target list")
    self.targetListSelectorArea = self.createHLayout([qt.QLabel("Target List: "), self.fiducialListSelector])
    self.targetListSelectorArea.hide()
    self.layout().addWidget(self.targetListSelectorArea)

  def setupTargetTable(self):
    self.table = qt.QTableWidget(0, 2)
    self.table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
    self.table.setSelectionMode(qt.QAbstractItemView.SingleSelection)
    self.table.setMaximumHeight(200)
    self.table.horizontalHeader().setStretchLastSection(True)
    self.resetTable()
    self.layout().addWidget(self.table)

  def setupButtons(self):
    self.startTargetingButton = self.createButton("", enabled=True, icon=self.setTargetsIcon, iconSize=self.ICON_SIZE,
                                                  toolTip="Start placing targets")
    self.stopTargetingButton = self.createButton("", enabled=False, icon=self.finishIcon, iconSize=self.ICON_SIZE,
                                                 toolTip="Finish placing targets")
    self.buttons = self.createHLayout([self.startTargetingButton, self.stopTargetingButton])
    self.layout().addWidget(self.buttons)

  def setupConnections(self):
    self.startTargetingButton.clicked.connect(self.startPlacing)
    self.stopTargetingButton.clicked.connect(self.stopPlacing)
    # TODO: think about the following since it will always listen!
    self.interactionNodeObserver = self.interactionNode.AddObserver(self.interactionNode.InteractionModeChangedEvent,
                                                                    self.onInteractionModeChanged)
    self.fiducialListSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onFiducialListSelected)
    self.table.connect("cellChanged (int,int)", self.onCellChanged)

  def onInteractionModeChanged(self, caller, event):
    if not self.currentNode:
      return
    if self.selectionNode.GetActivePlaceNodeID() == self.currentNode.GetID():
      interactionMode = self.interactionNode.GetCurrentInteractionMode()
      self.invokeEvent(self.TargetingStartedEvent if interactionMode == self.interactionNode.Place else
                       self.TargetingFinishedEvent)
      self.updateButtons()

  def onFiducialListSelected(self, node):
    self.currentNode = node

  def startPlacing(self):
    if not self.currentNode:
      self.createNewFiducialNode(name=self.DEFAULT_FIDUCIAL_LIST_NAME)
    self.selectionNode.SetReferenceActivePlaceNodeID(self.currentNode.GetID())
    self.interactionNode.SetPlaceModePersistence(1)
    self.interactionNode.SetCurrentInteractionMode(self.interactionNode.Place)

  def stopPlacing(self):
    self.interactionNode.SetCurrentInteractionMode(self.interactionNode.ViewTransform)

  def createNewFiducialNode(self, name=None):
    markupsLogic = slicer.modules.markups.logic()
    self.currentNode = slicer.mrmlScene.GetNodeByID(markupsLogic.AddNewFiducialNode())
    self.currentNode.SetName(name if name else self.currentNode.GetName())

  def resetTable(self):
    self.cleanupButtons()
    self.table.setRowCount(0)
    self.table.clear()
    self.table.setHorizontalHeaderLabels(self.HEADERS)

  def cleanupButtons(self):
    for button in self.connectedButtons:
      button.clicked.disconnect(self.handleDeleteButtonClicked)
    self.connectedButtons = []

  def removeTargetListObservers(self):
    if self.currentNode and len(self.fiducialNodeObservers) > 0:
      for observer in self.fiducialNodeObservers:
        self.currentNode.RemoveObserver(observer)
    self.fiducialNodeObservers = []

  def addTargetListObservers(self):
    if self.currentNode:
      for event in self.FIDUCIAL_LIST_OBSERVED_EVENTS:
        self.fiducialNodeObservers.append(self.currentNode.AddObserver(event, self.onFiducialsUpdated))

  def updateButtons(self):
    if not self.currentNode or self.currentNode.GetNumberOfFiducials() == 0:
      self.startTargetingButton.icon = self.setTargetsIcon
      self.startTargetingButton.toolTip = "Place Target(s)"
    else:
      self.startTargetingButton.icon = self.modifyTargetsIcon
      self.startTargetingButton.toolTip = "Modify Target(s)"
    interactionMode = self.interactionNode.GetCurrentInteractionMode()
    self.startTargetingButton.enabled = not interactionMode == self.interactionNode.Place
    self.stopTargetingButton.enabled = interactionMode == self.interactionNode.Place

  def updateTable(self):
    self.resetTable()
    if not self.currentNode:
      return
    nOfControlPoints = self.currentNode.GetNumberOfFiducials()
    if self.table.rowCount != nOfControlPoints:
      self.table.setRowCount(nOfControlPoints)
    for i in range(nOfControlPoints):
      label = self.currentNode.GetNthFiducialLabel(i)
      cellLabel = qt.QTableWidgetItem(label)
      self.table.setItem(i, 0, cellLabel)
      self.addDeleteButton(i, 1)

  def addDeleteButton(self, row, col):
    button = qt.QPushButton('X')
    self.table.setCellWidget(row, col, button)
    button.clicked.connect(lambda: self.handleDeleteButtonClicked(row))
    self.connectedButtons.append(button)

  def handleDeleteButtonClicked(self, idx):
    if slicer.util.confirmYesNoDisplay("Do you really want to delete fiducial %s?"
                                               % self.currentNode.GetNthFiducialLabel(idx), windowTitle="mpReview"):
      self.currentNode.RemoveMarkup(idx)

  def onFiducialsUpdated(self, caller, event):
    if caller.IsA("vtkMRMLMarkupsFiducialNode") and event == self.MODIFIED_EVENT:
      self.updateTable()
      self.updateButtons()
      self.invokeEvent(vtk.vtkCommand.ModifiedEvent)

  def onCellChanged(self, row, col):
    if col == 0:
      self.currentNode.SetNthFiducialLabel(row, self.table.item(row, col).text())

  def getOrCreateFiducialNode(self):
    node = self.fiducialListSelector.currentNode()
    if not node:
      node = self.fiducialListSelector.addNode()
    return node

  def hasTargetListAtLeastOneTarget(self):
    return self.currentNode is not None and self.currentNode.GetNumberOfFiducials() > 0


class SettingsMessageBox(qt.QMessageBox, ModuleWidgetMixin):

  def getSettingNames(self):
    return [s.replace(self.moduleName+"/", "") for s in list(qt.QSettings().allKeys()) if str.startswith(str(s),
                                                                                                         self.moduleName)]

  def __init__(self, moduleName, parent=None, **kwargs):
    self.moduleName = moduleName
    self.keyElementPairs = []
    qt.QMessageBox.__init__(self, parent, **kwargs)
    self.setup()
    self.adjustSize()

  def setup(self):
    self.setLayout(qt.QGridLayout())
    settingNames = self.getSettingNames()
    for index, setting in enumerate(settingNames):
      label = self.createLabel(setting)
      value = self.getSetting(setting)
      if value.lower() in ["true", "false"]:
        element = qt.QCheckBox()
        element.checked = value.lower() == "true"
      elif value.isdigit():
        element = qt.QSpinBox()
        element.value = int(value)
      elif os.path.exists(value):
        element = ctk.ctkPathLineEdit()
        if os.path.isdir(value):
          element.filters = ctk.ctkPathLineEdit.Dirs
        else:
          element.filters = ctk.ctkPathLineEdit.Files
        element.currentPath = value
      else:
        element = self.createLineEdit(value)
        element.minimumWidth = self.getMinimumTextWidth(element.text) + 10

      self.layout().addWidget(label, index, 0)
      self.layout().addWidget(element, index, 1, 1, qt.QSizePolicy.ExpandFlag)
      self.keyElementPairs.append((label.text, element))

    self.okButton = self.createButton("OK")
    self.cancelButton = self.createButton("Cancel")

    self.addButton(self.okButton, qt.QMessageBox.AcceptRole)
    self.addButton(self.cancelButton, qt.QMessageBox.NoRole)

    self.layout().addWidget(self.createHLayout([self.okButton, self.cancelButton]), len(settingNames), 1)
    self.okButton.clicked.connect(self.onOkButtonClicked)

  def getMinimumTextWidth(self, text):
    font = qt.QFont("", 0)
    metrics = qt.QFontMetrics(font)
    return metrics.width(text)

  def onOkButtonClicked(self):
    for key, element in self.keyElementPairs:
      if isinstance(element, qt.QCheckBox):
        value = "true" if element.checked else "false"
      elif isinstance(element, qt.QSpinBox):
        value = str(element.value)
      elif isinstance(element, ctk.ctkPathLineEdit):
        value = element.currentPath
      else:
        value = element.text
      if self.getSetting(key) != value:
        self.setSetting(key, value)
    self.close()


class ExtendedQMessageBox(qt.QMessageBox):

  def __init__(self, parent= None):
    super(ExtendedQMessageBox, self).__init__(parent)
    self.setupUI()

  def setupUI(self):
    self.checkbox = qt.QCheckBox("Remember the selection and do not notify again")
    self.layout().addWidget(self.checkbox, 1, 1)

  def exec_(self, *args, **kwargs):
    return qt.QMessageBox.exec_(self, *args, **kwargs), self.checkbox.isChecked()


class IncomingDataWindow(qt.QWidget, ModuleWidgetMixin):

  def __init__(self, incomingDataDirectory, title="Receiving image data",
               skipText="Skip", cancelText="Cancel", *args):
    super(IncomingDataWindow, self).__init__(*args)
    self.setWindowTitle(title)
    self.setWindowFlags(qt.Qt.CustomizeWindowHint | qt.Qt.WindowTitleHint | qt.Qt.WindowStaysOnTopHint)
    self.skipButtonText = skipText
    self.cancelButtonText = cancelText
    self.setup()
    self.dicomReceiver = SmartDICOMReceiver(incomingDataDirectory=incomingDataDirectory)
    self.dicomReceiver.addEventObserver(self.dicomReceiver.StatusChangedEvent, self.onStatusChanged)
    self.dicomReceiver.addEventObserver(self.dicomReceiver.IncomingDataReceiveFinishedEvent, self.onReceiveFinished)
    self.dicomReceiver.addEventObserver(self.dicomReceiver.IncomingFileCountChangedEvent, self.onReceivingData)
    self.dicomSender = None

  def __del__(self):
    super(IncomingDataWindow, self).__del__()
    if self.dicomReceiver:
      self.dicomReceiver.removeEventObservers()

  @vtk.calldata_type(vtk.VTK_STRING)
  def onStatusChanged(self, caller, event, callData):
    self.textLabel.text = callData

  @vtk.calldata_type(vtk.VTK_INT)
  def onReceivingData(self, caller, event, callData):
    self.skipButton.enabled = False
    self.directoryImportButton.enabled = False

  def show(self, disableWidget=None):
    self.disabledWidget = disableWidget
    if disableWidget:
      disableWidget.enabled = False
    qt.QWidget.show(self)
    self.dicomReceiver.start()

  def hide(self):
    if self.disabledWidget:
      self.disabledWidget.enabled = True
      self.disabledWidget = None
    qt.QWidget.hide(self)
    self.dicomReceiver.stop()

  def setup(self):
    self.setLayout(qt.QGridLayout())
    self.statusLabel = qt.QLabel("Status:")
    self.textLabel = qt.QLabel()
    self.layout().addWidget(self.statusLabel, 0, 0)
    self.layout().addWidget(self.textLabel, 0, 1, 1, 2)

    self.progress = qt.QProgressBar()
    self.progress.maximum = 0
    self.progress.setAlignment(qt.Qt.AlignCenter)

    self.layout().addWidget(self.progress, 1, 0, 1, qt.QSizePolicy.Maximum)

    self.buttonGroup = qt.QButtonGroup()
    self.skipButton = self.createButton(self.skipButtonText)
    self.cancelButton = self.createButton(self.cancelButtonText)
    self.directoryImportButton = self.createDirectoryButton(text="Import from directory",
                                                            caption="Choose directory to import DICOM data from")

    self.buttonGroup.addButton(self.skipButton)
    self.buttonGroup.addButton(self.cancelButton)
    self.layout().addWidget(self.skipButton, 2, 0)
    self.layout().addWidget(self.cancelButton, 2, 1)
    self.layout().addWidget(self.directoryImportButton, 2, 2)

    buttonHeight = 30
    for b in [self.skipButton, self.cancelButton, self.directoryImportButton]:
      b.minimumHeight = buttonHeight

    self.setupConnections()

  def setupConnections(self):
    self.buttonGroup.connect('buttonClicked(QAbstractButton*)', self.onButtonClicked)
    self.directoryImportButton.directorySelected.connect(self.onImportDirectorySelected)

  def onButtonClicked(self, button):
    self.hide()
    if button is self.skipButton:
      self.invokeEvent(SlicerDevelopmentToolboxEvents.IncomingDataSkippedEvent)
    else:
      self.invokeEvent(SlicerDevelopmentToolboxEvents.IncomingDataCanceledEvent)
      if self.dicomSender:
        self.dicomSender.stop()

  def onReceiveFinished(self, caller, event):
    self.hide()
    self.invokeEvent(SlicerDevelopmentToolboxEvents.IncomingDataReceiveFinishedEvent)

  def onImportDirectorySelected(self, directory):
    self.dicomSender = DICOMDirectorySender(directory, 'localhost', 11112)


class RatingWindow(qt.QWidget, ModuleWidgetMixin):

  @property
  def maximumValue(self):
    return self._maximumValue

  @maximumValue.setter
  def maximumValue(self, value):
    if value < 1:
      raise ValueError("The maximum rating value cannot be less than 1.")
    else:
      self._maximumValue = value

  def __init__(self, maximumValue, text="Please rate the registration result:", *args):
    qt.QWidget.__init__(self, *args)
    self.maximumValue = maximumValue
    self.text = text
    self.iconPath = os.path.join(os.path.dirname(sys.modules[self.__module__].__file__), '../Resources/Icons')
    self.setupIcons()
    self.setLayout(qt.QGridLayout())
    self.setWindowFlags(qt.Qt.WindowStaysOnTopHint | qt.Qt.FramelessWindowHint)
    self.setupElements()
    self.connectButtons()
    self.showRatingValue = True

  def __del__(self):
    super(RatingWindow, self).__del__()
    self.disconnectButtons()

  def isRatingEnabled(self):
    return not self.disableWidgetCheckbox.checked

  def setupIcons(self):
    self.filledStarIcon = self.createIcon("icon-star-filled.png", self.iconPath)
    self.unfilledStarIcon = self.createIcon("icon-star-unfilled.png", self.iconPath)

  def show(self, disableWidget=None):
    self.disabledWidget = disableWidget
    if disableWidget:
      disableWidget.enabled = False
    qt.QWidget.show(self)
    self.ratingScore = None

  def setupElements(self):
    self.layout().addWidget(qt.QLabel(self.text), 0, 0)
    self.ratingButtonGroup = qt.QButtonGroup()
    for rateValue in range(1, self.maximumValue+1):
      attributeName = "button"+str(rateValue)
      setattr(self, attributeName, self.createButton('', icon=self.unfilledStarIcon))
      self.ratingButtonGroup.addButton(getattr(self, attributeName), rateValue)

    for button in list(self.ratingButtonGroup.buttons()):
      button.setCursor(qt.Qt.PointingHandCursor)

    self.ratingLabel = self.createLabel("")
    row = self.createHLayout(list(self.ratingButtonGroup.buttons()) + [self.ratingLabel])
    self.layout().addWidget(row, 1, 0)

    self.disableWidgetCheckbox = qt.QCheckBox("Don't display this window again")
    self.disableWidgetCheckbox.checked = False
    self.layout().addWidget(self.disableWidgetCheckbox, 2, 0)

  def connectButtons(self):
    self.ratingButtonGroup.connect('buttonClicked(int)', self.onRatingButtonClicked)
    for button in list(self.ratingButtonGroup.buttons()):
      button.installEventFilter(self)

  def disconnectButtons(self):
    self.ratingButtonGroup.disconnect('buttonClicked(int)', self.onRatingButtonClicked)
    for button in list(self.ratingButtonGroup.buttons()):
      button.removeEventFilter(self)

  def eventFilter(self, obj, event):
    if obj in list(self.ratingButtonGroup.buttons()) and event.type() == qt.QEvent.HoverEnter:
      self.onHoverEvent(obj)
    elif obj in list(self.ratingButtonGroup.buttons()) and event.type() == qt.QEvent.HoverLeave:
      self.onLeaveEvent()
    return qt.QWidget.eventFilter(self, obj, event)

  def onLeaveEvent(self):
    for button in list(self.ratingButtonGroup.buttons()):
      button.icon = self.unfilledStarIcon

  def onHoverEvent(self, obj):
    ratingValue = 0
    for button in list(self.ratingButtonGroup.buttons()):
      button.icon = self.filledStarIcon
      ratingValue += 1
      if obj is button:
        break
    if self.showRatingValue:
      self.ratingLabel.setText(str(ratingValue))

  def onRatingButtonClicked(self, buttonId):
    self.ratingScore = buttonId
    if self.disabledWidget:
      self.disabledWidget.enabled = True
      self.disabledWidget = None
    self.invokeEvent(SlicerDevelopmentToolboxEvents.RatingWindowClosedEvent, str(self.ratingScore))
    self.hide()


class BasicInformationWatchBox(qt.QGroupBox):

  DEFAULT_STYLE = 'background-color: rgb(230,230,230)'
  PREFERRED_DATE_FORMAT = "%Y-%b-%d"

  def __init__(self, attributes, title="", parent=None, columns=1):
    super(BasicInformationWatchBox, self).__init__(title, parent)
    self.attributes = attributes
    self.columns = columns
    if not self.checkAttributeUniqueness():
      raise ValueError("Attribute names are not unique.")
    self.setup()

  def checkAttributeUniqueness(self):
    onlyNames = [attribute.name for attribute in self.attributes]
    return len(self.attributes) == len(set(onlyNames))

  def reset(self):
    for attribute in self.attributes:
      attribute.value = ""

  def setup(self):
    self.setStyleSheet(self.DEFAULT_STYLE)
    layout = qt.QGridLayout()
    self.setLayout(layout)

    column = 0
    for index, attribute in enumerate(self.attributes):
      layout.addWidget(attribute.titleLabel, index/self.columns, column*2, 1, 1, qt.Qt.AlignLeft)
      layout.addWidget(attribute.valueLabel, index/self.columns, column*2+1, 1, qt.Qt.AlignLeft)
      column = column+1 if column<self.columns-1 else 0

  def getAttribute(self, name):
    for attribute in self.attributes:
      if attribute.name == name:
        return attribute
    return None

  def setInformation(self, attributeName, value, toolTip=None):
    attribute = self.getAttribute(attributeName)
    attribute.value = value
    attribute.valueLabel.toolTip = toolTip

  def getInformation(self, attributeName):
    attribute = self.getAttribute(attributeName)
    return attribute.value if not attribute.masked else attribute.originalValue

  def formatDate(self, dateToFormat):
    if dateToFormat and dateToFormat != "":
      formatted = datetime.date(int(dateToFormat[0:4]), int(dateToFormat[4:6]), int(dateToFormat[6:8]))
      return formatted.strftime(self.PREFERRED_DATE_FORMAT)
    return "No Date found"

  def formatPatientName(self, name):
    if name != "":
      splitted = name.split('^')
      try:
        name = splitted[1] + ", " + splitted[0]
      except IndexError:
        name = splitted[0]
    return name


class FileBasedInformationWatchBox(BasicInformationWatchBox):

  DEFAULT_TAG_VALUE_SEPARATOR = ": "
  DEFAULT_TAG_NAME_SEPARATOR = "_"

  @property
  def sourceFile(self):
    return self._sourceFile

  @sourceFile.setter
  def sourceFile(self, filePath):
    self._sourceFile = filePath
    if not filePath:
      self.reset()
    self.updateInformation()

  def __init__(self, attributes, title="", sourceFile=None, parent=None, columns=1):
    super(FileBasedInformationWatchBox, self).__init__(attributes, title, parent, columns)
    if sourceFile:
      self.sourceFile = sourceFile

  def _getTagNameFromTagNames(self, tagNames):
    return self.DEFAULT_TAG_NAME_SEPARATOR.join(tagNames)

  def _getTagValueFromTagValues(self, values):
    return self.DEFAULT_TAG_VALUE_SEPARATOR.join(values)

  def updateInformation(self):
    for attribute in self.attributes:
      if attribute.callback:
        value = attribute.callback()
      else:
        value = self.updateInformationFromWatchBoxAttribute(attribute)
      self.setInformation(attribute.name, value, toolTip=value)

  def updateInformationFromWatchBoxAttribute(self, attribute):
    raise NotImplementedError


class XMLBasedInformationWatchBox(FileBasedInformationWatchBox):

  DATE_TAGS_TO_FORMAT = ["StudyDate", "PatientBirthDate", "SeriesDate", "ContentDate", "AcquisitionDate"]

  @FileBasedInformationWatchBox.sourceFile.setter
  def sourceFile(self, filePath):
    self._sourceFile = filePath
    if filePath:
      self.dom = xml.dom.minidom.parse(self._sourceFile)
    else:
      self.reset()
    self.updateInformation()

  def __init__(self, attributes, title="", sourceFile=None, parent=None, columns=1):
    super(XMLBasedInformationWatchBox, self).__init__(attributes, title, sourceFile, parent, columns)

  def reset(self):
    super(XMLBasedInformationWatchBox, self).reset()
    self.dom = None

  def updateInformationFromWatchBoxAttribute(self, attribute):
    if attribute.tags and self.dom:
      values = []
      for tag in attribute.tags:
        currentValue = ModuleLogicMixin.findElement(self.dom, tag)
        if tag in self.DATE_TAGS_TO_FORMAT:
          currentValue = self.formatDate(currentValue)
        elif tag == "PatientName":
          currentValue = self.formatPatientName(currentValue)
        values.append(currentValue)
      return self._getTagValueFromTagValues(values)
    return ""


class DICOMBasedInformationWatchBox(FileBasedInformationWatchBox):

  DATE_TAGS_TO_FORMAT = [DICOMTAGS.STUDY_DATE, DICOMTAGS.PATIENT_BIRTH_DATE]

  def __init__(self, attributes, title="", sourceFile=None, parent=None, columns=1):
    super(DICOMBasedInformationWatchBox, self).__init__(attributes, title, sourceFile, parent, columns)

  def updateInformationFromWatchBoxAttribute(self, attribute):
    if attribute.tags and self.sourceFile:
      values = []
      for tag in attribute.tags:
        currentValue = ModuleLogicMixin.getDICOMValue(self.sourceFile, tag, "")
        if tag in self.DATE_TAGS_TO_FORMAT:
          currentValue = self.formatDate(currentValue)
        elif tag == DICOMTAGS.PATIENT_NAME:
          currentValue = self.formatPatientName(currentValue)
        values.append(currentValue)
      return self._getTagValueFromTagValues(values)
    return ""