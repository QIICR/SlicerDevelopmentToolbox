import datetime
import logging
import os
import sys
import xml.dom

import ctk
import qt
import slicer
import vtk
from constants import DICOMTAGS
from decorators import singleton
from events import SlicerDevelopmentToolboxEvents
from helpers import SmartDICOMReceiver, DICOMDirectorySender
from mixins import ModuleWidgetMixin, ModuleLogicMixin


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

  @property
  def busy(self):
    return self.progress.minimum == 0 and self.progress.maximum == 0

  @busy.setter
  def busy(self, busy):
    if busy:
      self._oldMinimum = self.progress.minimum
      self._oldMaximum = self.progress.maximum
      self.progress.maximum = self.progress.minimum = 0
    else:
      self.progress.minimum = getattr(self, "_oldMinimum", 0)
      self.progress.maximum = getattr(self, "_oldMaximum", 100)
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
    if not self.parent():
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
  """ TargetCreationWidget is an exclusive QWidget for creating targets/fiducials

  Args:
    parent (qt.QWidget, optional): parent of the widget

  .. doctest::

    import ast
    import vtk

    @vtk.calldata_type(vtk.VTK_STRING)
    def onTargetSelected(caller, event, callData):
      info = ast.literal_eval(callData)
      node = slicer.mrmlScene.GetNodeByID(info["nodeID"])
      index = info["index"]
      print "%s clicked" % node.GetNthFiducialLabel(index)


    from SlicerDevelopmentToolboxUtils.widgets import TargetCreationWidget
    t = TargetCreationWidget()
    t.targetListSelectorVisible = True
    t.addEventObserver(t.TargetSelectedEvent, onTargetSelected)
    t.show()
  """

  _HEADERS = ["Name", "Delete"]

  DEFAULT_FIDUCIAL_LIST_NAME = None
  DEFAULT_CREATE_FIDUCIALS_TEXT = "Place Target(s)"
  DEFAULT_MODIFY_FIDUCIALS_TEXT = "Modify Target(s)"

  TargetingStartedEvent = vtk.vtkCommand.UserEvent + 335
  TargetingFinishedEvent = vtk.vtkCommand.UserEvent + 336
  TargetSelectedEvent = vtk.vtkCommand.UserEvent + 337

  @property
  def currentNode(self):
    """ Property for getting/setting current vtkMRMLMarkupsFiducialNode.

    currentNode represents the vtkMRMLMarkupsFiducialNode which is used for displaying/creating fiducials/targets.
    """
    return self.targetListSelector.currentNode()

  @currentNode.setter
  def currentNode(self, node):
    if self._currentNode:
      self.stopPlacing()
      self._removeTargetListObservers()
    self.targetListSelector.setCurrentNode(node)
    self._currentNode = node
    if node:
      self._addTargetListObservers()
      self._selectionNode.SetReferenceActivePlaceNodeID(node.GetID())
    else:
      self._selectionNode.SetReferenceActivePlaceNodeID(None)

    self._updateButtons()
    self._updateTable()

  @property
  def targetListSelectorVisible(self):
    """ Property for changing visibility of target list selector """
    return self.targetListSelectorArea.visible

  @targetListSelectorVisible.setter
  def targetListSelectorVisible(self, visible):
    self.targetListSelectorArea.visible = visible

  def __init__(self, parent=None, **kwargs):
    qt.QWidget.__init__(self, parent)
    self._iconPath = os.path.join(os.path.dirname(sys.modules[self.__module__].__file__), '../Resources/Icons')
    self._processKwargs(**kwargs)
    self._connectedButtons = []
    self._modifiedEventObserverTag = None
    self._selectionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSelectionNodeSingleton")
    self._interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
    self._setupIcons()
    self._setup()
    self._currentNode = None
    self._setupConnections()

  def reset(self):
    """ reset exits the fiducial/target placement mode and sets the currently observed vtkMRMLMarkupsFiducialNode to None
    """
    self.stopPlacing()
    self.currentNode = None

  def startPlacing(self):
    """ Enters the fiducial/target placement mode. """
    if not self.currentNode:
      self._createNewFiducialNode(name=self.DEFAULT_FIDUCIAL_LIST_NAME)
    self._selectionNode.SetReferenceActivePlaceNodeID(self.currentNode.GetID())
    self._interactionNode.SetPlaceModePersistence(1)
    self._interactionNode.SetCurrentInteractionMode(self._interactionNode.Place)

  def stopPlacing(self):
    """ Exits the fiducial/target placement mode.
    """
    self._interactionNode.SetCurrentInteractionMode(self._interactionNode.ViewTransform)

  def getOrCreateFiducialNode(self):
    """ Convenience method for getting (or creating if it doesn't exist) current vtkMRMLMarkupsFiducialNode"""
    if not self.currentNode:
      self.currentNode = self.targetListSelector.addNode()
    return self.currentNode

  def hasTargetListAtLeastOneTarget(self):
    """ Returns if currently observed vtkMRMLMarkupsFiducialNode has at least one fiducial

      Returns:
        bool: True if vtkMRMLMarkupsFiducialNode is not None and number of fiducials in vtkMRMLMarkupsFiducialNode is
        unequal zero, False otherwise

    """
    return self.currentNode is not None and self.currentNode.GetNumberOfFiducials() > 0

  def _setupIcons(self):
    self._iconSize = qt.QSize(24, 24)
    self.addTargetsIcon = self.createIcon("icon-addFiducial.png", self._iconPath)
    self.modifyTargetsIcon = self.createIcon("icon-modifyFiducial.png", self._iconPath)
    self.finishTargetingIcon = self.createIcon("icon-apply.png", self._iconPath)

  def _setup(self):
    self.setLayout(qt.QGridLayout())
    self._setupTargetFiducialListSelector()
    self._setupTargetTable()
    self._setupButtons()

  def _setupTargetFiducialListSelector(self):
    self.targetListSelector = self.createComboBox(nodeTypes=["vtkMRMLMarkupsFiducialNode", ""], addEnabled=True,
                                                  removeEnabled=True, noneEnabled=True, showChildNodeTypes=False,
                                                  selectNodeUponCreation=True, toolTip="Select target list")
    self.targetListSelectorArea = self.createHLayout([qt.QLabel("Target List: "), self.targetListSelector])
    self.targetListSelectorArea.hide()
    self.layout().addWidget(self.targetListSelectorArea)

  def _setupTargetTable(self):
    self.table = qt.QTableWidget(0, 2)
    self.table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
    self.table.setSelectionMode(qt.QAbstractItemView.SingleSelection)
    self.table.setMaximumHeight(200)
    self.table.horizontalHeader().setStretchLastSection(True)
    self._resetTable()
    self.layout().addWidget(self.table)

  def _setupButtons(self):
    self.startTargetingButton = self.createButton("", enabled=True, icon=self.addTargetsIcon, iconSize=self._iconSize,
                                                  toolTip="Start placing targets")
    self.stopTargetingButton = self.createButton("", enabled=False, icon=self.finishTargetingIcon, iconSize=self._iconSize,
                                                 toolTip="Finish placing targets")
    self.buttons = self.createHLayout([self.startTargetingButton, self.stopTargetingButton])
    self.layout().addWidget(self.buttons)

  def _setupConnections(self):
    self.startTargetingButton.clicked.connect(self.startPlacing)
    self.stopTargetingButton.clicked.connect(self.stopPlacing)
    self.interactionNodeObserver = self._interactionNode.AddObserver(self._interactionNode.InteractionModeChangedEvent,
                                                                     self._onInteractionModeChanged)
    self.targetListSelector.connect("currentNodeChanged(vtkMRMLNode*)", self._onFiducialListSelected)
    self.table.connect("cellChanged (int,int)", self._onCellChanged)
    self.table.connect('clicked(QModelIndex)', self._onTargetSelectionChanged)

  def _onTargetSelectionChanged(self, modelIndex):
    self.invokeEvent(self.TargetSelectedEvent, str({"nodeID": self.currentNode.GetID(),
                                                    "index": modelIndex.row()}))

  def _onInteractionModeChanged(self, caller, event):
    if not self.currentNode:
      return
    if self._selectionNode.GetActivePlaceNodeID() == self.currentNode.GetID():
      interactionMode = self._interactionNode.GetCurrentInteractionMode()
      self.invokeEvent(self.TargetingStartedEvent if interactionMode == self._interactionNode.Place else
                       self.TargetingFinishedEvent)
      self._updateButtons()

  def _onFiducialListSelected(self, node):
    self.currentNode = node

  def _createNewFiducialNode(self, name=None):
    markupsLogic = slicer.modules.markups.logic()
    self.currentNode = slicer.mrmlScene.GetNodeByID(markupsLogic.AddNewFiducialNode())
    self.currentNode.SetName(name if name else self.currentNode.GetName())

  def _cleanupButtons(self):
    for button in self._connectedButtons:
      button.clicked.disconnect(self._handleDeleteButtonClicked)
    self._connectedButtons = []

  def _removeTargetListObservers(self):
    if self.currentNode and self._modifiedEventObserverTag:
      self._modifiedEventObserverTag = self.currentNode.RemoveObserver(self._modifiedEventObserverTag)

  def _addTargetListObservers(self):
    self._removeTargetListObservers()
    if self.currentNode:
      self._modifiedEventObserverTag = self.currentNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self._onFiducialsUpdated)

  def _updateButtons(self):
    if not self.currentNode or self.currentNode.GetNumberOfFiducials() == 0:
      self.startTargetingButton.icon = self.addTargetsIcon
      self.startTargetingButton.toolTip = "Place Target(s)"
    else:
      self.startTargetingButton.icon = self.modifyTargetsIcon
      self.startTargetingButton.toolTip = "Modify Target(s)"
    interactionMode = self._interactionNode.GetCurrentInteractionMode()
    self.startTargetingButton.enabled = not interactionMode == self._interactionNode.Place
    self.stopTargetingButton.enabled = interactionMode == self._interactionNode.Place

  def _updateTable(self):
    self._resetTable()
    if not self.currentNode:
      return
    nOfControlPoints = self.currentNode.GetNumberOfFiducials()
    if self.table.rowCount != nOfControlPoints:
      self.table.setRowCount(nOfControlPoints)
    for i in range(nOfControlPoints):
      label = self.currentNode.GetNthFiducialLabel(i)
      cellLabel = qt.QTableWidgetItem(label)
      self.table.setItem(i, 0, cellLabel)
      self._addDeleteButton(i, 1)

  def _resetTable(self):
    self._cleanupButtons()
    self.table.setRowCount(0)
    self.table.clear()
    self.table.setHorizontalHeaderLabels(self._HEADERS)

  def _addDeleteButton(self, row, col):
    button = qt.QPushButton('X')
    self.table.setCellWidget(row, col, button)
    button.clicked.connect(lambda: self._handleDeleteButtonClicked(row))
    self._connectedButtons.append(button)

  def _handleDeleteButtonClicked(self, idx):
    if slicer.util.confirmYesNoDisplay("Do you really want to delete target %s?"
                                         % self.currentNode.GetNthFiducialLabel(idx)):
      self.currentNode.RemoveMarkup(idx)

  def _onFiducialsUpdated(self, caller, event):
    if caller.IsA("vtkMRMLMarkupsFiducialNode") and event == "ModifiedEvent":
      self._updateTable()
      self._updateButtons()
      self.invokeEvent(vtk.vtkCommand.ModifiedEvent)

  def _onCellChanged(self, row, col):
    if col == 0:
      self.currentNode.SetNthFiducialLabel(row, self.table.item(row, col).text())


class SettingsMessageBox(qt.QMessageBox, ModuleWidgetMixin):
  """ QMessageBox that displays qt.QSettings defined for module 'moduleName'

  Args:
      moduleName (str): name of the module which qt.QSettings you want to view/modify
      parent (qt.QWidget, optional): parent of the widget

  .. doctest::

    from SlicerDevelopmentToolboxUtils.widgets import SettingsMessageBox
    s = SettingsMessageBox(moduleName='DICOM')
    s.show()


  See Also: :paramref:`SlicerDevelopmentToolboxUtils.buttons.ModuleSettingsButton`
  """

  def __init__(self, moduleName, parent=None, **kwargs):
    self.moduleName = moduleName
    self._elements = []
    qt.QMessageBox.__init__(self, parent, **kwargs)
    self._setup()
    self.adjustSize()

  def _setup(self):
    self.setLayout(qt.QGridLayout())
    self.okButton = self.createButton("OK")
    self.cancelButton = self.createButton("Cancel")

    self.addButton(self.okButton, qt.QMessageBox.AcceptRole)
    self.addButton(self.cancelButton, qt.QMessageBox.NoRole)

    self.layout().addWidget(self.createHLayout([self.okButton, self.cancelButton]), 1, 1, 1, 2)
    self.okButton.clicked.connect(self._onOkButtonClicked)

  def _createUIFromSettings(self):
    if getattr(self, "settingGroupBox", None):
      self.settingGroupBox.setParent(None)
      del self.settingGroupBox
    self.settingGroupBox = qt.QGroupBox()
    self.settingGroupBox.setStyleSheet("QGroupBox{border:0;}")
    self.settingGroupBox.setLayout(qt.QGridLayout())
    self._elements = []
    for index, setting in enumerate(self._getSettingNames()):
      label = self.createLabel(setting)
      value = self.getSetting(setting)

      if isinstance(value, tuple) or isinstance(value, list):
        element = qt.QListWidget()
        element.setProperty("type", type(value))
        map(element.addItem, value)
      elif isinstance(value, qt.QSize) or isinstance(value, qt.QPoint):
        if isinstance(value, qt.QSize):
          element = SizeEdit(value.width(), value.height())
        else:
          element = PointEdit(value.x(), value.y())
        element.setProperty("type", type(value))
        element.addEventObserver(element.ModifiedEvent, lambda caller, event, e=element: self._onAttributeModified(e))
      else:
        value = str(value)
        if value.lower() in ["true", "false"]:
          element = qt.QCheckBox()
          element.checked = value.lower() == "true"
          element.toggled.connect(lambda enabled, e=element: self._onAttributeModified(e))
        elif value.isdigit():
          element = qt.QSpinBox()
          element.setMaximum(999999)
          element.value = int(value)
          element.valueChanged.connect(lambda newVal, e=element: self._onAttributeModified(e))
        elif os.path.exists(value):
          element = ctk.ctkPathLineEdit()
          if os.path.isdir(value):
            element.filters = ctk.ctkPathLineEdit.Dirs
          else:
            element.filters = ctk.ctkPathLineEdit.Files
          element.currentPath = value
          element.currentPathChanged.connect(lambda path, e=element: self._onAttributeModified(e))
        else:
          element = self.createLineEdit(value)
          element.minimumWidth = self._getMinimumTextWidth(element.text) + 10
          element.textChanged.connect(lambda text, e=element: self._onAttributeModified(e))

      if element:
        element.setProperty("modified", False)
        element.setProperty("attributeName", label.text)
        self.settingGroupBox.layout().addWidget(label, index, 0)
        self.settingGroupBox.layout().addWidget(element, index, 1, 1, qt.QSizePolicy.ExpandFlag)
        self._elements.append(element)
    self.layout().addWidget(self.settingGroupBox, 0, 1, 1, 2)

  def _getSettingNames(self):
    keys = list(qt.QSettings().allKeys())
    return [s.replace(self.moduleName + "/", "") for s in keys if str.startswith(str(s), self.moduleName)]

  def show(self):
    """ Displays the settings QMessageBox... All necessary ui components will be build depending on the settings type.
    """
    self._createUIFromSettings()
    qt.QMessageBox.show(self)

  def hide(self):
    """ Hides the settings QMessageBox

    Note: Usually this method would not be used because once the QMessageBox is displayed, everything else in the
          background will be disabled and is not accessible until the QMessageBox is closed.
    """
    qt.QMessageBox.hide(self)

  def _onAttributeModified(self, element):
    element.setProperty("modified", True)

  def _getMinimumTextWidth(self, text):
    font = qt.QFont("", 0)
    metrics = qt.QFontMetrics(font)
    return metrics.width(text)

  def _onOkButtonClicked(self):
    for element in self._elements:
      if not element.property("modified"):
        continue
      if isinstance(element, qt.QCheckBox):
        value = element.checked
      elif isinstance(element, qt.QSpinBox):
        value = str(element.value)
      elif isinstance(element, ctk.ctkPathLineEdit):
        value = element.currentPath
      elif isinstance(element, qt.QListWidget):
        if element.property("type") is tuple:
          value = (element.item(i).text() for i in range(element.count))
        else:
          value = [element.item(i).text() for i in range(element.count)]
      elif isinstance(element, SizeEdit):
        value = qt.QSize(element.width, element.height)
      elif isinstance(element, PointEdit):
        value = qt.QPoint(element.x, element.y)
      else:
        value = element.text
      attributeName = element.property("attributeName")
      if not self.hasSetting(attributeName):
        raise ValueError("QSetting attribute {}/{} does not exist".format(self.moduleName, attributeName))
      if self.getSetting(attributeName) != value:
        logging.debug("Setting value %s for attribute %s" %(value, attributeName))
        self.setSetting(attributeName, value)
    self.close()


class DimensionEditBase(qt.QWidget, ModuleWidgetMixin):
  """ Base class widget for two dimensional inputs."""

  ModifiedEvent = vtk.vtkCommand.UserEvent + 2324

  def __init__(self, first, second, parent=None):
    super(DimensionEditBase, self).__init__(parent)
    self._setup(first, second)
    self._setupConnections()

  def _setup(self, first, second):
    self.setLayout(qt.QHBoxLayout())
    self.firstDimension = qt.QSpinBox()
    self.firstDimension.maximum = 9999
    self.firstDimension.setValue(first)
    self.secondDimension = qt.QSpinBox()
    self.secondDimension.maximum = 9999
    self.secondDimension.setValue(second)
    self.layout().addWidget(self.firstDimension)
    self.layout().addWidget(self.secondDimension)

  def _setupConnections(self):
    self.firstDimension.valueChanged.connect(self._onValueChanged)
    self.secondDimension.valueChanged.connect(self._onValueChanged)

  def _onValueChanged(self, value):
    self.invokeEvent(self.ModifiedEvent)


class SizeEdit(DimensionEditBase):
  """ Widget representing a spinbox for width and another for height."""

  @property
  def width(self):
    """horizontal extent"""
    return self.firstDimension.value

  @width.setter
  def width(self, width):
    self.firstDimension.value = width

  @property
  def height(self):
    """vertical extent"""
    return self.secondDimension.value

  @height.setter
  def height(self, height):
    self.secondDimension.value = height

  def __init__(self, width, height, parent=None):
    super(SizeEdit, self).__init__(width, height, parent)


class PointEdit(DimensionEditBase):
  """ Widget for displaying two dimensional position. One spinbox for x and another for y."""

  @property
  def x(self):
    """x position"""
    return self.firstDimension.value

  @x.setter
  def x(self, x):
    self.firstDimension.value = x

  @property
  def y(self):
    """y position"""
    return self.secondDimension.value

  @y.setter
  def y(self, y):
    self.secondDimension.value = y

  def __init__(self, x, y, parent=None):
    super(PointEdit, self).__init__(x, y, parent)


class ExtendedQMessageBox(qt.QMessageBox):
  """ QMessageBox which is extended by an additional checkbox for remembering selection without notifying again."""

  def __init__(self, parent= None):
    super(ExtendedQMessageBox, self).__init__(parent)
    self.setupUI()

  def setupUI(self):
    self.checkbox = qt.QCheckBox("Remember the selection and do not notify again")
    self.layout().addWidget(self.checkbox, 1, 1)

  def exec_(self, *args, **kwargs):
    return qt.QMessageBox.exec_(self, *args, **kwargs), self.checkbox.isChecked()


class IncomingDataWindow(qt.QWidget, ModuleWidgetMixin):
  """ Reception/import window for DICOM data into a specified directory sent via storescu or from a selected directory.

  Besides running a DICOM receiver via storescp in the background, the operator also can choose to import recursively
  from a directory. Once reception has finished, the window will automatically be hidden.

  Note: The used port for incoming DICOM data is '11112'

  Args:
    incomingDataDirectory (str): directory where the received DICOM files will be stored
    incomingPort (str, optional): port on which DICOM images are expected to be received
    title (str, optional): window title
    skipText (str, optional): text to be displayed for the skip button
    cancelText (str, optional): text to be displayed for the cancel button

  .. doctest::

    def onReceptionFinished(caller, event):
      print "Reception finished"

    from SlicerDevelopmentToolboxUtils.widgets import IncomingDataWindow

    window = IncomingDataWindow(slicer.app.temporaryPath)
    window.addEventObserver(window.IncomingDataReceiveFinishedEvent, onReceptionFinished)
    window.show()

    # receive data on port 11112 and wait for slot to be called

  See Also: :paramref:`SlicerDevelopmentToolboxUtils.helpers.SmartDICOMReceiver`

  """

  IncomingDataSkippedEvent = SlicerDevelopmentToolboxEvents.IncomingDataSkippedEvent
  """Invoked when skip button was used"""
  IncomingDataCanceledEvent = SlicerDevelopmentToolboxEvents.IncomingDataCanceledEvent
  """Invoked when cancel button was used"""
  IncomingDataReceiveFinishedEvent = SlicerDevelopmentToolboxEvents.IncomingDataReceiveFinishedEvent
  """Invoked when reception has finished"""

  def __init__(self, incomingDataDirectory, incomingPort=None, title="Receiving image data", skipText="Skip",
               cancelText="Cancel", *args):
    super(IncomingDataWindow, self).__init__(*args)
    self.setWindowTitle(title)
    self.setWindowFlags(qt.Qt.CustomizeWindowHint | qt.Qt.WindowTitleHint | qt.Qt.WindowStaysOnTopHint)
    self.skipButtonText = skipText
    self.cancelButtonText = cancelText
    self.incomingPort = incomingPort
    self._setup()
    self._setupConnections()
    self._setupDICOMReceiver(incomingDataDirectory)
    self.dicomSender = None

  def __del__(self):
    super(IncomingDataWindow, self).__del__()
    if self.dicomReceiver:
      self.dicomReceiver.removeEventObservers()

  @vtk.calldata_type(vtk.VTK_STRING)
  def _onStatusChanged(self, caller, event, callData):
    self.textLabel.text = callData

  @vtk.calldata_type(vtk.VTK_INT)
  def _onReceivingData(self, caller, event, callData):
    self.skipButton.enabled = False
    self.directoryImportButton.enabled = False

  def show(self, disableWidget=None):
    """ Opens the window and starts the DICOM reception process

    Args:
      disableWidget (qt.QWidget, optional): widget that needs to get disabled once IncomingDataWindow opens
    """
    self.disabledWidget = disableWidget
    if disableWidget:
      disableWidget.enabled = False
    qt.QWidget.show(self)
    self.dicomReceiver.start()

  def hide(self):
    """ Closes the window, stops the DICOM reception process, and enables the widget that has been disabled (optional)
    """
    if self.disabledWidget:
      self.disabledWidget.enabled = True
      self.disabledWidget = None
    qt.QWidget.hide(self)
    self.dicomReceiver.stop()

  def _setup(self):
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

  def _setupConnections(self):
    self.buttonGroup.connect('buttonClicked(QAbstractButton*)', self._onButtonClicked)
    self.directoryImportButton.directorySelected.connect(self._onImportDirectorySelected)

  def _setupDICOMReceiver(self, incomingDataDirectory):
    self.dicomReceiver = SmartDICOMReceiver(incomingDataDirectory=incomingDataDirectory,
                                            incomingPort=self.incomingPort)
    self.dicomReceiver.addEventObserver(self.dicomReceiver.StatusChangedEvent, self._onStatusChanged)
    self.dicomReceiver.addEventObserver(self.dicomReceiver.IncomingDataReceiveFinishedEvent, self._onReceptionFinished)
    self.dicomReceiver.addEventObserver(self.dicomReceiver.IncomingFileCountChangedEvent, self._onReceivingData)

  def _onButtonClicked(self, button):
    self.hide()
    if button is self.skipButton:
      self.invokeEvent(self.IncomingDataSkippedEvent)
    else:
      self.invokeEvent(self.IncomingDataCanceledEvent)
      if self.dicomSender:
        self.dicomSender.stop()

  def _onReceptionFinished(self, caller, event):
    self.hide()
    self.invokeEvent(self.IncomingDataReceiveFinishedEvent)

  def _onImportDirectorySelected(self, directory):
    self.dicomSender = DICOMDirectorySender(directory, 'localhost', 11112)


class RatingWindow(qt.QWidget, ModuleWidgetMixin):

  RatingWindowClosedEvent = vtk.vtkCommand.UserEvent + 304

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
    self._connectButtons()
    self.showRatingValue = True

  def __del__(self):
    super(RatingWindow, self).__del__()
    self._disconnectButtons()

  def isRatingEnabled(self):
    return not self.disableWidgetCheckbox.checked

  def setupIcons(self):
    self.filledStarIcon = self.createIcon("icon-star-filled.png", self.iconPath)
    self.unfilledStarIcon = self.createIcon("icon-star-unfilled.png", self.iconPath)

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

  def _connectButtons(self):
    self.ratingButtonGroup.connect('buttonClicked(int)', self.onRatingButtonClicked)
    for button in list(self.ratingButtonGroup.buttons()):
      button.installEventFilter(self)

  def _disconnectButtons(self):
    self.ratingButtonGroup.disconnect('buttonClicked(int)', self.onRatingButtonClicked)
    for button in list(self.ratingButtonGroup.buttons()):
      button.removeEventFilter(self)

  def show(self, disableWidget=None):
    self.disabledWidget = disableWidget
    if disableWidget:
      disableWidget.enabled = False
    qt.QWidget.show(self)
    self.ratingScore = None

  def eventFilter(self, obj, event):
    if obj in list(self.ratingButtonGroup.buttons()) and event.type() == qt.QEvent.HoverEnter:
      self._onHoverEvent(obj)
    elif obj in list(self.ratingButtonGroup.buttons()) and event.type() == qt.QEvent.HoverLeave:
      self._onLeaveEvent()
    return qt.QWidget.eventFilter(self, obj, event)

  def _onLeaveEvent(self):
    for button in list(self.ratingButtonGroup.buttons()):
      button.icon = self.unfilledStarIcon

  def _onHoverEvent(self, obj):
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
    self.invokeEvent(self.RatingWindowClosedEvent, str(self.ratingScore))
    self.hide()


class BasicInformationWatchBox(qt.QGroupBox):
  """ BasicInformationWatchBox can be used for displaying key:value pairs in a qt.QGroupBox.

  Args:
    attributes (list): list of WatchBoxAttributes
    title (str,optional): text to be displayed in the upper left corner of the BasicInformationWatchBox
    parent (qt.QWidget, optional): parent of the button
    columns (int, optional): number of columns in which key/value pairs will be displayed
  """

  _DEFAULT_STYLE = 'background-color: rgb(230,230,230)'
  _dateFormat = "%Y-%b-%d"

  @staticmethod
  def _formatPatientName(name):
    if name != "":
      splitted = name.split('^')
      try:
        name = splitted[1] + ", " + splitted[0]
      except IndexError:
        name = splitted[0]
    return name

  def __init__(self, attributes, title="", parent=None, columns=1):
    super(BasicInformationWatchBox, self).__init__(title, parent)
    self.attributes = attributes
    self.columns = columns
    if not self._checkAttributeUniqueness():
      raise ValueError("Attribute names are not unique.")
    self._setup()

  def reset(self):
    """ Sets all values (not keys) to ''
    """
    for attribute in self.attributes:
      attribute.value = ""

  def _checkAttributeUniqueness(self):
    onlyNames = [attribute.name for attribute in self.attributes]
    return len(self.attributes) == len(set(onlyNames))

  def _setup(self):
    self.setStyleSheet(self._DEFAULT_STYLE)
    layout = qt.QGridLayout()
    self.setLayout(layout)

    column = 0
    for index, attribute in enumerate(self.attributes):
      layout.addWidget(attribute.titleLabel, index/self.columns, column*2, 1, 1, qt.Qt.AlignLeft)
      layout.addWidget(attribute.valueLabel, index/self.columns, column*2+1, 1, qt.Qt.AlignLeft)
      column = column+1 if column<self.columns-1 else 0

  def _formatDate(self, dateToFormat):
    if dateToFormat and dateToFormat != "":
      formatted = datetime.date(int(dateToFormat[0:4]), int(dateToFormat[4:6]), int(dateToFormat[6:8]))
      return formatted.strftime(self._dateFormat)
    return "No Date found"

  def setPreferredDateFormat(self, dateFormat):
    """ Setting the preferred format dates should be displayed

    See Also:  https://docs.python.org/2/library/datetime.html#datetime.datetime.strftime
    """
    self._dateFormat = dateFormat

  def setInformation(self, attributeName, value, toolTip=None):
    attribute = self.getAttribute(attributeName)
    attribute.value = value
    attribute.valueLabel.toolTip = toolTip

  def getInformation(self, attributeName):
    """ Retrieve information by delivering the attribute name.

      Returns:
        value if WatchBoxAttribute was set to masked else the original value
    """
    attribute = self.getAttribute(attributeName)
    return attribute.value if not attribute.masked else attribute.originalValue

  def getAttribute(self, name):
    """ Retrieve attribute by attribute name.

      Returns:
        None if attribute name was not found else WatchBoxAttribute
    """
    for attribute in self.attributes:
      if attribute.name == name:
        return attribute
    return None


class FileBasedInformationWatchBox(BasicInformationWatchBox):

  DEFAULT_TAG_VALUE_SEPARATOR = ": "
  DEFAULT_TAG_NAME_SEPARATOR = "_"

  @property
  def sourceFile(self):
    self._sourceFile = getattr(self, "_sourceFile", None)
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
          currentValue = self._formatDate(currentValue)
        elif tag == "PatientName":
          currentValue = self._formatPatientName(currentValue)
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
          currentValue = self._formatDate(currentValue)
        elif tag == DICOMTAGS.PATIENT_NAME:
          currentValue = self._formatPatientName(currentValue)
        values.append(currentValue)
      return self._getTagValueFromTagValues(values)
    return ""