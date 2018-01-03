import datetime
import logging
import os
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
from icons import Icons


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
      if not (self.progress.minimum == 0 and self.progress.maximum == 0):
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
    self.reset()

  def setup(self):

    self.textLabel = qt.QLabel()
    self.progress = qt.QProgressBar()

    if slicer.util.mainWindow():
      self.maximumHeight = slicer.util.mainWindow().statusBar().height
    rowLayout = qt.QHBoxLayout()
    self.setLayout(rowLayout)
    rowLayout.addWidget(self.textLabel, 1)
    rowLayout.addWidget(self.progress, 1)
    self.setStyleSheet(self.STYLE)
    self.refreshProgressVisibility()
    if not self.parent() and slicer.util.mainWindow():
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

  .. image:: images/TargetCreationWidget.gif

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
  """ Default fiducial list name to be used """
  DEFAULT_CREATE_FIDUCIALS_TEXT = "Place Target(s)"
  """ Default text to be displayed for the startTargetingButton """
  DEFAULT_MODIFY_FIDUCIALS_TEXT = "Modify Target(s)"
  """ Default text to be displayed after creation for the startTargetingButton """

  StartedEvent = SlicerDevelopmentToolboxEvents.StartedEvent
  """ Targeting mode was activated"""
  FinishedEvent = SlicerDevelopmentToolboxEvents.FinishedEvent
  """ Targeting was finished """
  TargetSelectedEvent = vtk.vtkCommand.UserEvent + 337
  """ Target selection changed 
  
  Slot to be called once 
    
  .. doctest::
    import ast
    import vtk
     
    @vtk.calldata_type(vtk.VTK_STRING)
    def onTargetSelected(caller, event, callData):
      info = ast.literal_eval(callData)
      print info["index"]
      print info["nodeID"]
  
  """

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
    self._processKwargs(**kwargs)
    self._connectedButtons = []
    self._modifiedEventObserverTag = None
    self._selectionNode = slicer.app.applicationLogic().GetSelectionNode()
    self._selectionNode.SetReferenceActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
    self._interactionNode = slicer.app.applicationLogic().GetInteractionNode()
    self._setupIcons()
    self._setup()
    self._currentNode = None

  def reset(self):
    """ exits the fiducial/target placement mode and sets the currently observed vtkMRMLMarkupsFiducialNode to None
    """
    self.stopPlacing()
    self.currentNode = None

  def startPlacing(self):
    """ Enters the fiducial/target placement mode. """
    if not self.currentNode:
      self._createNewFiducialNode(name=self.DEFAULT_FIDUCIAL_LIST_NAME)

    self._selectionNode.SetActivePlaceNodeID(self.currentNode.GetID())
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
    self.addTargetsIcon = Icons.fiducial_add
    self.modifyTargetsIcon = Icons.fiducial_modify
    self.finishTargetingIcon = Icons.apply

  def _setup(self):
    self.setLayout(qt.QGridLayout())
    self._setupTargetFiducialListSelector()
    self._setupTargetTable()
    self._setupButtons()
    self._setupConnections()

  def _setupTargetFiducialListSelector(self):
    self.targetListSelector = self.createComboBox(nodeTypes=["vtkMRMLMarkupsFiducialNode", ""], addEnabled=True,
                                                  removeEnabled=True, noneEnabled=True, showChildNodeTypes=False,
                                                  renameEnabled=True, selectNodeUponCreation=True,
                                                  toolTip="Select target list")
    self.targetListSelectorArea = self.createHLayout([qt.QLabel("Target List: "), self.targetListSelector])
    self.targetListSelectorArea.hide()
    self.layout().addWidget(self.targetListSelectorArea)

  def _setupTargetTable(self):
    self.table = qt.QTableWidget(0, 2)
    self.table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
    self.table.setSelectionMode(qt.QAbstractItemView.SingleSelection)
    self.table.setMaximumHeight(200)
    self.table.horizontalHeader().setResizeMode(qt.QHeaderView.Stretch)
    self.table.horizontalHeader().setResizeMode(0, qt.QHeaderView.Stretch)
    self.table.horizontalHeader().setResizeMode(1, qt.QHeaderView.ResizeToContents)
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
    self.table.connect("cellChanged(int,int)", self._onCellChanged)
    self.table.connect('clicked(QModelIndex)', self._onTargetSelectionChanged)
    self.table.selectionModel().currentRowChanged.connect(self._onTargetSelectionChanged)

  def _onTargetSelectionChanged(self, current, prev=None):
    row = current.row()
    if not self.currentNode or row == -1:
      return
    self.invokeEvent(self.TargetSelectedEvent, str({"nodeID": self.currentNode.GetID(),
                                                    "index": row}))

  def _onInteractionModeChanged(self, caller, event):
    if not self.currentNode:
      return
    if self._selectionNode.GetActivePlaceNodeID() == self.currentNode.GetID():
      interactionMode = self._interactionNode.GetCurrentInteractionMode()
      self.invokeEvent(self.StartedEvent if interactionMode == self._interactionNode.Place else
                       self.FinishedEvent)
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
  """ QMessageBox for displaying qt.QSettings defined for module 'moduleName'.

  Normally Settings are defined in groups e.g. DICOM/{subgroup(optional)}/{settingsName}

  .. image:: images/SettingsMessageBox.png
    :width: 50%

  Args:
    moduleNames (list, optional):
      name of the module(s) which qt.QSettings you want to view/modify
      if None, all available subgroups from qt.QSettings will be setup in tabs
    parent (qt.QWidget, optional):
      parent of the widget

  .. code-block:: python
    :caption: Display settings for MORE THAN ONE module/group

    from SlicerDevelopmentToolboxUtils.widgets import SettingsMessageBox
    s = SettingsMessageBox(moduleNames=['Developer', 'DICOM'])
    s.show()

  .. code-block:: python
    :caption: Display settings for ONE module/group

    from SlicerDevelopmentToolboxUtils.widgets import SettingsMessageBox
    s = SettingsMessageBox(moduleNames='DICOM')
    s.show()

  .. code-block:: python
    :caption: Display settings for ALL available modules/groups

    from SlicerDevelopmentToolboxUtils.widgets import SettingsMessageBox
    s = SettingsMessageBox() # displays all available settings that are in groups
    s.show()

  See Also: :paramref:`SlicerDevelopmentToolboxUtils.buttons.ModuleSettingsButton`
  """

  def __init__(self, moduleNames=None, parent=None, **kwargs):
    self.moduleNames = [moduleNames] if type(moduleNames) is str else moduleNames
    qt.QMessageBox.__init__(self, parent, **kwargs)
    self._setup()
    self.adjustSize()

  def cleanup(self):
    """Cleans up the 'old' settings groupbox"""
    if getattr(self, "settingGroupBox", None):
      self.settingsTabWidget.setParent(None)
      del self.settingsTabWidget

  def show(self):
    """ Displays the settings QMessageBox... All necessary ui components will be build depending on the settings type.
    """
    self._createUIFromSettings()
    qt.QMessageBox.show(self)

  def _setup(self):
    self.setLayout(qt.QGridLayout())
    self.okButton = self.createButton("OK")
    self.cancelButton = self.createButton("Cancel")

    self.addButton(self.okButton, qt.QMessageBox.AcceptRole)
    self.addButton(self.cancelButton, qt.QMessageBox.NoRole)

    self.layout().addWidget(self.createHLayout([self.okButton, self.cancelButton]), 1, 1, 1, 2)
    self.okButton.clicked.connect(self._onOkButtonClicked)

  def _createUIFromSettings(self):
    self.cleanup()
    self._elements = []
    self.settings = qt.QSettings()
    self.settingsTabWidget = qt.QTabWidget()
    moduleNames = self.moduleNames if self.moduleNames and len(self.moduleNames) else self._getSettingGroups()
    for moduleName in moduleNames:
      self._addModuleTab(moduleName)
    self.layout().addWidget(self.settingsTabWidget, 0, 1, 1, 2)

  def _addModuleTab(self, moduleName):
    tabWidget = qt.QFrame()
    tabWidget.setLayout(qt.QFormLayout())
    self.settingsTabWidget.addTab(tabWidget, moduleName)
    self._addSettingsGroup(moduleName, tabWidget)

  def _addSettingsGroup(self, name, parent):
    widget = qt.QFrame() if isinstance(parent, qt.QFrame) else qt.QGroupBox(name)
    widget.setLayout(qt.QFormLayout())

    self.settings.beginGroup(name)
    for setting in self._getSettingAttributes():
      self._addSettingsAttribute(widget, setting)
    for groupName in self._getSettingGroups():
      self._addSettingsGroup(groupName, widget.layout())
    self.settings.endGroup()

    parentLayout = parent.layout()
    if isinstance(parentLayout, qt.QHBoxLayout):
      parentLayout.addWidget(widget)
    else:
      parentLayout.addRow(widget)

  def _getSettingAttributes(self):
    separator = "/"
    return filter(lambda x: separator not in x, self.settings.allKeys())

  def _getSettingGroups(self):
    separator = "/"
    groups = set()
    for subgroup in filter(lambda x: separator in x, self.settings.allKeys()):
      groups.add(subgroup.split(separator)[0])
    return groups

  def _addSettingsAttribute(self, groupBox, setting):
    value = self.settings.value(setting)
    group = self.settings.group() + "/" if self.settings.group() else ""
    if isinstance(value, tuple) or isinstance(value, list):
      element = qt.QListWidget()
      element.setProperty("type", type(value))
      map(element.addItem, value)
    elif isinstance(value, qt.QSize) or isinstance(value, qt.QPoint):
      element = self._createDimensionalElement(value)
    elif isinstance(value, qt.QByteArray):
      logging.debug("Skipping %s which is a QByteArray" % group+setting)
      return
    else:
      value = str(value)
      if value.lower() in ["true", "false"]:
        element = self._createCheckBox(value)
      elif value.isdigit():
        element = self._createSpinBox(value)
      elif os.path.exists(value):
        element = self._createPathLineEdit(value)
      else:
        element = self._createLineEdit(value)
    if element:
      element.setProperty("modified", False)
      element.setProperty("attributeName", group+setting)
      groupBox.layout().addRow(setting, element)
      self._elements.append(element)

  def _createDimensionalElement(self, value):
    if isinstance(value, qt.QSize):
      dimElement = SizeEdit(value.width(), value.height())
    else:
      dimElement = PointEdit(value.x(), value.y())
    dimElement.setProperty("type", type(value))
    dimElement.addEventObserver(dimElement.ModifiedEvent, lambda caller, event, e=dimElement: self._onAttributeModified(e))
    return dimElement

  def _createLineEdit(self, value):
    lineEdit = self.createLineEdit(value, toolTip=value)
    lineEdit.minimumWidth = self._getMinimumTextWidth(lineEdit.text) + 10
    lineEdit.textChanged.connect(lambda text, e=lineEdit: self._onAttributeModified(e))
    return lineEdit

  def _createPathLineEdit(self, value):
    pathLineEdit = ctk.ctkPathLineEdit()
    if os.path.isdir(value):
      pathLineEdit.filters = ctk.ctkPathLineEdit.Dirs
    else:
      pathLineEdit.filters = ctk.ctkPathLineEdit.Files
    pathLineEdit.currentPath = value
    pathLineEdit.toolTip =value
    pathLineEdit.currentPathChanged.connect(lambda path, e=pathLineEdit: self._onAttributeModified(e))
    return pathLineEdit

  def _createSpinBox(self, value):
    spinbox = qt.QSpinBox()
    spinbox.setMaximum(999999)
    spinbox.value = int(value)
    spinbox.valueChanged.connect(lambda newVal, e=spinbox: self._onAttributeModified(e))
    return spinbox

  def _createCheckBox(self, value):
    checkbox = qt.QCheckBox()
    checkbox.checked = value.lower() == "true"
    checkbox.toggled.connect(lambda enabled, e=checkbox: self._onAttributeModified(e))
    return checkbox

  def _onAttributeModified(self, element):
    element.setProperty("modified", True)

  def _getMinimumTextWidth(self, text):
    font = qt.QFont("", 0)
    metrics = qt.QFontMetrics(font)
    return metrics.width(text)

  def _onOkButtonClicked(self):
    self.settings = qt.QSettings()
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
      if not self.settings.contains(attributeName):
        raise ValueError("QSetting attribute {} does not exist".format(attributeName))
      if self.settings.value(attributeName) != value:
        logging.debug("Setting value %s for attribute %s" %(value, attributeName))
        self.settings.setValue(attributeName, value)
    self.close()


class DimensionEditBase(qt.QWidget, ModuleWidgetMixin):
  """ Base class widget for two dimensional inputs."""

  ModifiedEvent = vtk.vtkCommand.UserEvent + 2324
  """ Will be invoked whenever first or second dimension changes. """

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
    self.setup()

  def setup(self):
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
    window.addEventObserver(window.FinishedEvent, onReceptionFinished)
    window.show()

    # receive data on port 11112 and wait for slot to be called

  See Also: :paramref:`SlicerDevelopmentToolboxUtils.helpers.SmartDICOMReceiver`

  """

  SkippedEvent = SlicerDevelopmentToolboxEvents.SkippedEvent
  """Invoked when skip button was used"""
  CanceledEvent = SlicerDevelopmentToolboxEvents.CanceledEvent
  """Invoked when cancel button was used"""
  FinishedEvent = SlicerDevelopmentToolboxEvents.FinishedEvent
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
    self.dicomReceiver = SmartDICOMReceiver(destinationDirectory=incomingDataDirectory,
                                            incomingPort=self.incomingPort)
    self.dicomReceiver.addEventObserver(self.dicomReceiver.StatusChangedEvent, self._onStatusChanged)
    self.dicomReceiver.addEventObserver(self.dicomReceiver.IncomingDataReceiveFinishedEvent, self._onReceptionFinished)
    self.dicomReceiver.addEventObserver(self.dicomReceiver.FileCountChangedEvent, self._onReceivingData)

  def _onButtonClicked(self, button):
    self.hide()
    if button is self.skipButton:
      self.invokeEvent(self.SkippedEvent)
    else:
      self.invokeEvent(self.CanceledEvent)
      if self.dicomSender:
        self.dicomSender.stop()

  def _onReceptionFinished(self, caller, event):
    self.hide()
    self.invokeEvent(self.FinishedEvent)

  def _onImportDirectorySelected(self, directory):
    self.dicomSender = DICOMDirectorySender(directory, 'localhost', 11112)


class RatingMessageBox(qt.QMessageBox, ModuleWidgetMixin):
  """ Provides a qt.QMessageBox with a number of stars (equivalent to maximum value) for rating e.g. a result.

  .. image:: images/RatingMessageBox.png
    :width: 40%

  The number of stars is equivalent to the maximum rating value. Additionally there is a checkbox for preventing
  the message box to be displayed again. The logic for not displaying it though needs to be implemented by the
  user.

  Args:

    maximumValue (int): Maximum rating value
    text (str, optional): Text to be displayed for the rating window.

  .. code-block:: python
    :caption: Display RatingMessageBox and invoke event once rating is done

    import vtk

    @vtk.calldata_type(vtk.VTK_INT)
    def onRatingFinished(caller, event, ratingValue):
      print "Rating finished with rating value %d" % ratingValue

    def onRatingCanceled(caller, event):
      print "Rating was canceled"

    from SlicerDevelopmentToolboxUtils.widgets import RatingMessageBox

    rating = RatingMessageBox(maximumValue=10)
    rating.addEventObserver(rating.FinishedEvent, onRatingFinished)
    rating.addEventObserver(rating.CanceledEvent, onRatingCanceled)
    rating.show()
  """

  CanceledEvent = SlicerDevelopmentToolboxEvents.CanceledEvent
  """ Invoked when RatingMessageBox was closed without any rating. """
  FinishedEvent = SlicerDevelopmentToolboxEvents.FinishedEvent
  """ Invoked once a rating value has been selected. """

  @property
  def maximumValue(self):
    """ Maximum rating value. """
    return self._maximumValue

  @maximumValue.setter
  def maximumValue(self, value):
    if value < 1:
      raise ValueError("The maximum rating value cannot be less than 1.")
    else:
      self._maximumValue = value

  def __init__(self, maximumValue, text="Please rate the result", *args):
    qt.QMessageBox.__init__(self, *args)
    self.maximumValue = maximumValue
    self.text = text
    self._setupIcons()
    self._setup()

  def __del__(self):
    super(RatingMessageBox, self).__del__()
    for button in self.buttons():
      self._disconnectButton(button)

  def isRatingEnabled(self):
    """ Returns if rating is enabled. Depends on the checkbox displayed within the widget.

    Returns:
      bool: checkbox 'Don't display this window again' is unchecked. By default it is unchecked so the return value
      would be True.
    """
    return not self.disableWidgetCheckbox.checked

  def show(self):
    """ Opens the window
    """
    self.ratingScore = None
    self.ratingLabel.text = " "
    qt.QMessageBox.show(self)

  def reject(self):
    """ Rejects rating and invokes CanceledEvent. """
    qt.QMessageBox.reject(self)

  def closeEvent(self, event):
    """ Is called when close button is pressed. Invokes CanceledEvent. """
    self.invokeEvent(self.CanceledEvent)
    qt.QMessageBox.closeEvent(self, event)
    self.reject()

  def _setupIcons(self):
    self.filledStarIcon = Icons.star_filled
    self.unfilledStarIcon = Icons.star_unfilled

  def _setup(self):
    for rateValue in range(1, self.maximumValue+1):
      button = self.createButton('', icon=self.unfilledStarIcon)
      button.setProperty('value', rateValue)
      button.setCursor(qt.Qt.PointingHandCursor)
      button.installEventFilter(self)
      self._connectButton(button)
      self.addButton(button, qt.QMessageBox.AcceptRole)

    self.ratingLabel = self.createLabel(" ")
    width = self._getMinimumTextWidth(len(str(self.maximumValue))*" ")
    self.ratingLabel.setFixedSize(width+12, 30)

    row = self.createHLayout(list(self.buttons()) + [self.ratingLabel])
    self.layout().addWidget(row, 2, 1)

    self.disableWidgetCheckbox = qt.QCheckBox("Don't display this window again")
    self.disableWidgetCheckbox.checked = False
    self.layout().addWidget(self.disableWidgetCheckbox, 4, 1)

  def _connectButton(self, button):
    button.clicked.connect(lambda: self._onRatingButtonClicked(button.value))

  def _disconnectButton(self, button):
    button.clicked.disconnect(lambda: self._onRatingButtonClicked(button.value))

  def eventFilter(self, obj, event):
    if obj in self.buttons() and event.type() == qt.QEvent.HoverEnter:
      self._onHoverEvent(obj)
    elif obj in self.buttons() and event.type() == qt.QEvent.HoverLeave:
      self._onLeaveEvent()
    return qt.QWidget.eventFilter(self, obj, event)

  def _onLeaveEvent(self):
    for button in self.buttons():
      button.icon = self.unfilledStarIcon

  def _onHoverEvent(self, obj):
    ratingValue = 0
    for button in self.buttons():
      button.icon = self.filledStarIcon
      ratingValue += 1
      if obj is button:
        break
    self.ratingLabel.setText(str(ratingValue))

  def _onRatingButtonClicked(self, value):
    self.ratingScore = value
    self.invokeEvent(self.FinishedEvent, self.ratingScore)


class BasicInformationWatchBox(qt.QGroupBox):
  """ BasicInformationWatchBox can be used for displaying basic information like patient name, birthday, but also other.

  .. |bpw1| image:: images/BasicPatientWatchBox_one_colum.png
  .. |bpw2| image:: images/BasicPatientWatchBox_two_colums.png
  .. |bpw3| image:: images/BasicPatientWatchBox_three_colums.png

  +-----------+---------------+-----------------+
  | One column|  Two columns  |  Three columns  |
  +===========+===============+=================+
  |   |bpw1|  |     |bpw2|    |     |bpw3|      |
  +-----------+---------------+-----------------+

  Args:
    attributes (list): list of WatchBoxAttributes
    title (str, optional): text to be displayed in the upper left corner of the BasicInformationWatchBox
    parent (qt.QWidget, optional): parent of the button
    columns (int, optional): number of columns in which key/value pairs will be displayed

  .. code-block:: python
    :caption: Display some basic information about a patient

    from SlicerDevelopmentToolboxUtils.helpers import WatchBoxAttribute
    from SlicerDevelopmentToolboxUtils.widgets import BasicInformationWatchBox
    from datetime import datetime

    patientWatchBoxInformation = [WatchBoxAttribute('PatientName', 'Name: '),
                                  WatchBoxAttribute('PatientID', 'PID: '),
                                  WatchBoxAttribute('StudyDate', 'Study Date: ')]

    patientWatchBox = BasicInformationWatchBox(patientWatchBoxInformation, title="Patient Information")
    patientWatchBox.show()

    patientWatchBox.setInformation('PatientName', 'Doe, John')
    patientWatchBox.setInformation('PatientID', '12345')
    patientWatchBox.setInformation('StudyDate', datetime.now().strftime("%Y_%m_%d"))

  See Also:
    :paramref:`SlicerDevelopmentToolboxUtils.helpers.WatchBoxAttribute`

    :paramref:`SlicerDevelopmentToolboxUtils.widgets.FileBasedInformationWatchBox`

    :paramref:`SlicerDevelopmentToolboxUtils.widgets.XMLBasedInformationWatchBox`

    :paramref:`SlicerDevelopmentToolboxUtils.widgets.DICOMBasedInformationWatchBox`

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
    if columns <= 0:
      raise ValueError("Number of columns cannot be smaller than 1")
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
    self.setLayout(qt.QGridLayout())

    def addPairAndReturnNewColumn(title, value, row, column):
      self.layout().addWidget(title, row, column*2, 1, 1, qt.Qt.AlignLeft)
      self.layout().addWidget(value, row, column*2+1, 1, 1, qt.Qt.AlignLeft)
      return column+1 if column<self.columns-1 else 0

    column = 0
    for index, attribute in enumerate(self.attributes):
      column = addPairAndReturnNewColumn(attribute.titleLabel, attribute.valueLabel, index/self.columns, column)

    while column != 0 and column <= self.columns-1:
      column = addPairAndReturnNewColumn(qt.QLabel(""), qt.QLabel(""), index/self.columns, column)

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
  """ FileBasedInformationWatchBox is a base class for file based information that should be displayed in a watchbox

  See Also:
    :paramref:`SlicerDevelopmentToolboxUtils.helpers.WatchBoxAttribute`

    :paramref:`SlicerDevelopmentToolboxUtils.widgets.BasicInformationWatchBox`
  """

  DEFAULT_TAG_VALUE_SEPARATOR = ": "
  DEFAULT_TAG_NAME_SEPARATOR = "_"

  @property
  def sourceFile(self):
    """ Source file which information should be displayed in the watchbox. """
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
    """ Forcing information to be updated from files.

    If no callback is implemented for the attribute, the information will be updated from WatchBoxAttribute.

    """
    for attribute in self.attributes:
      if attribute.callback:
        value = attribute.callback()
      else:
        value = self.updateInformationFromWatchBoxAttribute(attribute)
      self.setInformation(attribute.name, value, toolTip=value)

  def updateInformationFromWatchBoxAttribute(self, attribute):
    """ This method implements the strategy how watchbox information are retrieve from files.

    Note: This method needs to be implemented by inheriting classes.
    """
    raise NotImplementedError


class XMLBasedInformationWatchBox(FileBasedInformationWatchBox):
  """ XMLBasedInformationWatchBox is based on xml file based information that should be displayed in a watchbox.

  .. image:: images/XMLBasedInformationWatchBox.png

  .. code-block:: python
    :caption: Display information retrieved from a xml file

    from SlicerDevelopmentToolboxUtils.helpers import WatchBoxAttribute
    from SlicerDevelopmentToolboxUtils.widgets import XMLBasedInformationWatchBox
    import os

    watchBoxInformation = [WatchBoxAttribute('PatientName', 'Name:', 'PatientName'),
                           WatchBoxAttribute('StudyDate', 'Study Date:', 'StudyDate'),
                           WatchBoxAttribute('PatientID', 'PID:', 'PatientID'),
                           WatchBoxAttribute('PatientBirthDate', 'DOB:', 'PatientBirthDate')]

    informationWatchBox = XMLBasedInformationWatchBox(watchBoxInformation, columns=2)

    informationWatchBox.sourceFile = os.path.join(os.path.dirname(slicer.util.modulePath("SlicerDevelopmentToolbox")),
                                                  "doc", "data", "XMLBasedInformationWatchBoxTest.xml")
    informationWatchBox.show()

  See Also:
    :paramref:`SlicerDevelopmentToolboxUtils.helpers.WatchBoxAttribute`

    :paramref:`SlicerDevelopmentToolboxUtils.widgets.FileBasedInformationWatchBox`

    :paramref:`SlicerDevelopmentToolboxUtils.widgets.BasicInformationWatchBox`
  """

  DATE_TAGS_TO_FORMAT = ["StudyDate", "PatientBirthDate", "SeriesDate", "ContentDate", "AcquisitionDate"]
  """ A list of date attributes names as defined for every WatchBoxAttribute that needs to be formatted
  
  See Also:
    :paramref:`SlicerDevelopmentToolboxUtils.helpers.WatchBoxAttribute`
  """

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
  """ DICOMBasedInformationWatchBox is based on information retrieved from DICOM that should be displayed in a watchbox.

  .. image:: images/DICOMBasedInformationWatchBox.png

  .. code-block:: python
    :caption: Display information retrieved from a DICOM file

    from SlicerDevelopmentToolboxUtils.helpers import WatchBoxAttribute
    from SlicerDevelopmentToolboxUtils.widgets import DICOMBasedInformationWatchBox
    from SlicerDevelopmentToolboxUtils.constants import DICOMTAGS
    import os

    WatchBoxAttribute.TRUNCATE_LENGTH = 20
    watchBoxInformation = [WatchBoxAttribute('PatientName', 'Name: ', DICOMTAGS.PATIENT_NAME),
                           WatchBoxAttribute('PatientID', 'PID: ', DICOMTAGS.PATIENT_ID),
                           WatchBoxAttribute('DOB', 'DOB: ', DICOMTAGS.PATIENT_BIRTH_DATE)]

    informationWatchBox = DICOMBasedInformationWatchBox(watchBoxInformation, title="Patient Information")

    filename = "1.3.6.1.4.1.43046.3.330964839400343291362242315939623549555"
    informationWatchBox.sourceFile = os.path.join(os.path.dirname(slicer.util.modulePath("SlicerDevelopmentToolbox")),
                                                  "doc", "data", filename)
    informationWatchBox.show()


  See Also:
    :paramref:`SlicerDevelopmentToolboxUtils.helpers.WatchBoxAttribute`

    :paramref:`SlicerDevelopmentToolboxUtils.widgets.FileBasedInformationWatchBox`

    :paramref:`SlicerDevelopmentToolboxUtils.widgets.BasicInformationWatchBox`
  """

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


class DICOMConnectionTestWidget(qt.QDialog, ModuleWidgetMixin):
  """ Dialog for testing network connectivity specifically for DICOM reception.

  .. |pic1| image:: images/DICOMConnectionTestWidget_initial_status.png
  .. |pic2| image:: images/DICOMConnectionTestWidget_waiting_status.png
  .. |pic3| image:: images/DICOMConnectionTestWidget_success_status.png

  +--------+-----------+-----------+
  | Initial|  Waiting  |  Success  |
  +========+===========+===========+
  | |pic1| |  |pic2|   |   |pic3|  |
  +--------+-----------+-----------+

  Can be used to test the reception of DICOM data on a specified port. Once the start buttons is clickeda temporary
  directory will be created under slicer.app.temporaryPath. Closing the dialog  will stop the DICOM receiver (in case
  it's running) and the temporarily created directory will be deleted.

  Args:
    incomingPort (str, optional): port on which DICOM data is expected to be received. Default: 11112
    parent (qt.QWidget, optional): parent of the widget

  .. doctest::

    from SlicerDevelopmentToolboxUtils.widgets import DICOMConnectionTestWidget
    dicomTestWidget = DICOMConnectionTestWidget()
    dicomTestWidget.show()
  """

  __Initial_Style = 'background-color: indianred; color: black;'
  __Waiting_Style = 'background-color: gold; color: black;'
  __Success_Style = 'background-color: green; color: white;'

  __Initial_Status_Text = "Not Running."
  __Success_Status_Text = "DICOM connection successfully tested!"

  SuccessEvent = SlicerDevelopmentToolboxEvents.SuccessEvent

  def __init__(self, incomingPort="11112", parent=None):
    qt.QDialog.__init__(self, parent)
    self.__dicomReceiver = None
    self.__incomingPort = incomingPort
    self.modal = True
    self.success = False
    self.setup()

  def setup(self):
    """ Setup user interface including signal connections"""
    self.setLayout(qt.QGridLayout())
    self.incomingPortSpinBox = qt.QSpinBox()
    self.incomingPortSpinBox.setMaximum(65535)
    if self.__incomingPort:
      self.incomingPortSpinBox.setValue(int(self.__incomingPort))
    self.startButton = self.createButton("Start")
    self.stopButton = self.createButton("Stop", enabled=False)
    self.statusEdit = self.createLineEdit(self.__Initial_Status_Text, enabled=False)
    self.statusEdit.setStyleSheet(self.__Initial_Style)

    self.layout().addWidget(qt.QLabel("Port:"), 0, 0)
    self.layout().addWidget(self.incomingPortSpinBox, 0, 1)
    self.layout().addWidget(qt.QLabel("Status:"), 1, 0)
    self.layout().addWidget(self.statusEdit, 1, 1)
    self.layout().addWidget(self.startButton, 2, 0)
    self.layout().addWidget(self.stopButton, 2, 1)
    self._setupConnections()

  def show(self):
    """Displays the dialog"""
    self.statusEdit.setText(self.__Initial_Status_Text)
    qt.QDialog.show(self)

  def hide(self):
    """Hides the dialog, stops the DICOM receiver in case it is running and deletes the temporarily created directory"""
    self._cleanup()
    qt.QDialog.hide()

  def reject(self):
    """Rejects the dialog and cleans up DICOM receiver and temporarily created directory"""
    self._cleanup()
    qt.QDialog.reject(self)

  def _setupConnections(self):
    self.startButton.clicked.connect(self._onStartButtonClicked)
    self.stopButton.clicked.connect(self._onStopButtonClicked)
    self.statusEdit.textChanged.connect(self._onStatusEditTextChanged)
    self.incomingPortSpinBox.valueChanged.connect(lambda value: self.statusEdit.setText(self.__Initial_Status_Text))

  def _onStartButtonClicked(self):
    self.startButton.enabled = False
    self.incomingPortSpinBox.enabled = False
    self.stopButton.enabled = True
    self._start()

  def _start(self):
    from datetime import datetime
    directory = os.path.join(slicer.app.temporaryPath, datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
    ModuleLogicMixin.createDirectory(directory)
    self.__dicomReceiver = SmartDICOMReceiver(directory, self.incomingPortSpinBox.value)
    self.__dicomReceiver.addEventObserver(SmartDICOMReceiver.StatusChangedEvent, self._onDICOMReceiverStatusChanged)
    self.__dicomReceiver.addEventObserver(SmartDICOMReceiver.FileCountChangedEvent, self._onFilesReceived)
    self.__dicomReceiver.start()
    self.statusEdit.setStyleSheet(self.__Waiting_Style)

  @vtk.calldata_type(vtk.VTK_STRING)
  def _onDICOMReceiverStatusChanged(self, caller, event, callData):
    self.statusEdit.setText(callData)
    self.statusEdit.setStyleSheet(self.__Initial_Style)

  @vtk.calldata_type(vtk.VTK_INT)
  def _onFilesReceived(self, caller, event, count):
    self._onStopButtonClicked()
    self.statusEdit.setText(self.__Success_Status_Text)
    self.statusEdit.setStyleSheet(self.__Success_Style)
    self.invokeEvent(self.SuccessEvent)

  def _onStopButtonClicked(self):
    self.startButton.enabled = True
    self.incomingPortSpinBox.enabled = True
    self.stopButton.enabled = False
    self.__dicomReceiver.stop()
    self.__dicomReceiver.removeEventObservers()
    self.statusEdit.setText(self.__Initial_Status_Text)
    self.statusEdit.setStyleSheet(self.__Initial_Style)

  def _onStatusEditTextChanged(self, text):
    width = self._getMinimumTextWidth(text)
    if width > self.statusEdit.width:
      self.statusEdit.setFixedSize(width+12, self.statusEdit.height) # border width: 2+2 and padding: 8 = 2+2+8=12

  def _cleanup(self):
    if self.__dicomReceiver:
      if self.__dicomReceiver.isRunning():
        self._onStopButtonClicked()

      try:
        import shutil
        shutil.rmtree(self.__dicomReceiver.destinationDirectory)
      except OSError:
        pass
      finally:
        self.__dicomReceiver = None


class ImportIntoSegmentationWidgetBase(qt.QWidget, ModuleWidgetMixin):

  StartedEvent = SlicerDevelopmentToolboxEvents.StartedEvent
  FailedEvent = SlicerDevelopmentToolboxEvents.FailedEvent
  SuccessEvent = SlicerDevelopmentToolboxEvents.SuccessEvent

  _LayoutClass = None

  @property
  def busy(self):
    return self._busy

  @property
  def segmentationNodeSelectorVisible(self):
    return self.segmentationNodeSelector.visible

  @segmentationNodeSelectorVisible.setter
  def segmentationNodeSelectorVisible(self, visible):
    self.segmentationNodeSelector.visible = visible
    self.segmentationLabel.visible = visible

  @property
  def segmentationNodeSelectorEnabled(self):
    return self.currentSegmentationNodeSelector.enabled

  @segmentationNodeSelectorEnabled.setter
  def segmentationNodeSelectorEnabled(self, enabled):
    self.currentSegmentationNodeSelector.enabled = enabled

  def __init__(self, parent=None):
    qt.QWidget.__init__(self, parent)
    self._busy = False
    self.setup()
    self._setupConnections()

  def setup(self):
    self.segmentationNodeSelector = self._createSegmentationNodeSelector()
    if not self._LayoutClass:
      raise NotImplementedError
    self.setLayout(self._LayoutClass())

  def _setupConnections(self):
    raise NotImplementedError

  def invokeEvent(self, event, callData=None):
    self._busy = event == self.StartedEvent
    ModuleWidgetMixin.invokeEvent(self, event, callData)

  def setSegmentationNode(self, segmentationNode):
    if segmentationNode and not isinstance(segmentationNode, slicer.vtkMRMLSegmentationNode):
      raise ValueError("The delivered node needs to be a vtkMRMLSegmentationNode")
    self.segmentationNodeSelector.setCurrentNode(segmentationNode)

  def _createSegmentationNodeSelector(self):
    return self.createComboBox(nodeTypes=["vtkMRMLSegmentationNode", ""],showChildNodeTypes=False,
                               selectNodeUponCreation=False, toolTip="Select Segmentation")


class CopySegmentBetweenSegmentationsWidget(ImportIntoSegmentationWidgetBase):
  """ This widget can be used to move/copy segments between two segmentations or import labelmaps into a segmentation

  .. code-block:: python

    from SlicerDevelopmentToolboxUtils.widgets import CopySegmentBetweenSegmentationsWidget

    w = CopySegmentBetweenSegmentationsWidget()

    w.show()

  """

  _LayoutClass = qt.QGridLayout

  @property
  def currentSegmentationNodeSelector(self):
    return self.segmentationNodeSelector

  def __init__(self, parent=None):
    super(CopySegmentBetweenSegmentationsWidget, self).__init__(parent)

  def setup(self):
    super(CopySegmentBetweenSegmentationsWidget, self).setup()

    self.relatedUIElements = {}
    self.currentSegmentsTableView = self._createSegmentsTableView()
    self.relatedUIElements[self.currentSegmentationNodeSelector] = self.currentSegmentsTableView

    iconSize = qt.QSize(36,36)
    self.moveCurrentToOtherButton = self.createButton("", toolTip="Move segment", icon=Icons.move_to_right,
                                                      iconSize=iconSize, enabled=False)
    self.copyCurrentToOtherButton = self.createButton("", toolTip="Copy segment", icon=Icons.copy_to_right,
                                                      iconSize=iconSize, enabled=False)
    self.copyOtherToCurrentButton = self.createButton("", toolTip="Copy segment", icon=Icons.copy_to_left,
                                                      iconSize=iconSize, enabled=False)
    self.moveOtherToCurrentButton = self.createButton("", toolTip="Move segment", icon=Icons.move_to_left,
                                                      iconSize=iconSize, enabled=False)

    self.otherSegmentationNodeSelector = self._createSegmentationNodeSelector()
    self.otherSegmentsTableView = self._createSegmentsTableView()
    self.relatedUIElements[self.otherSegmentationNodeSelector] = self.otherSegmentsTableView

    self.infoLabel = self.createLabel("", enabled=False)

    self.layout().addWidget(self.currentSegmentationNodeSelector, 0, 0)
    self.layout().addWidget(self.otherSegmentationNodeSelector, 0, 2)
    self.layout().addWidget(self.currentSegmentsTableView, 1, 0, 4, 1)
    self.layout().addWidget(self.otherSegmentsTableView, 1, 2, 4, 1)
    self.layout().addWidget(self.copyCurrentToOtherButton, 1, 1)
    self.layout().addWidget(self.moveCurrentToOtherButton, 2, 1)
    self.layout().addWidget(self.copyOtherToCurrentButton, 3, 1)
    self.layout().addWidget(self.moveOtherToCurrentButton, 4, 1)
    self.layout().addWidget(self.infoLabel, 5, 0, 1, 3)

  def createButton(self, title, **kwargs):
    button = qt.QToolButton()
    button.text = title
    button.setCursor(qt.Qt.PointingHandCursor)
    button = self.extendQtGuiElementProperties(button, **kwargs)
    button.setSizePolicy(qt.QSizePolicy.Minimum, qt.QSizePolicy.Expanding)
    return button

  def _createSegmentsTableView(self):
    tableView = slicer.qMRMLSegmentsTableView()
    tableView.setHeaderVisible(False)
    tableView.setVisibilityColumnVisible(False)
    tableView.setOpacityColumnVisible(False)
    tableView.setColorColumnVisible(False)
    tableView.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
    tableView.SegmentsTableMessageLabel.hide()
    return tableView

  def _setupConnections(self):
    self.currentSegmentationNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)',
                                         lambda node: self._onSegmentationSelected(self.currentSegmentationNodeSelector,
                                                                                   node,
                                                                                   self.otherSegmentationNodeSelector))
    self.otherSegmentationNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)',
                                         lambda node: self._onSegmentationSelected(self.otherSegmentationNodeSelector,
                                                                                   node,
                                                                                   self.currentSegmentationNodeSelector))

    self.currentSegmentsTableView.selectionChanged.connect(lambda selected, deselected: self.updateView())
    self.otherSegmentsTableView.selectionChanged.connect(lambda selected, deselected: self.updateView())

    self.copyCurrentToOtherButton.clicked.connect(lambda: self._copySegmentsBetweenSegmentations(True, False))
    self.copyOtherToCurrentButton.clicked.connect(lambda: self._copySegmentsBetweenSegmentations(False, False))
    self.moveCurrentToOtherButton.clicked.connect(lambda: self._copySegmentsBetweenSegmentations(True, True))
    self.moveOtherToCurrentButton.clicked.connect(lambda: self._copySegmentsBetweenSegmentations(False, True))

  def _onSegmentationSelected(self, selector, node, contrary):
    tableView = self.relatedUIElements[selector]
    message = ""
    if node and node is contrary.currentNode():
      node = None
      message = "Warning: Cannot have the same segmentation selected on both sides"
    selector.setCurrentNode(node)
    tableView.setSegmentationNode(node)
    tableView.SegmentsTableMessageLabel.hide()
    self.infoLabel.setText(message)
    self.updateView()

  def updateView(self):
    valid = self.currentSegmentationNodeSelector.currentNode() and self.otherSegmentationNodeSelector.currentNode()
    self.copyCurrentToOtherButton.enabled = valid and len(self.currentSegmentsTableView.selectedSegmentIDs())
    self.copyOtherToCurrentButton.enabled = valid and len(self.otherSegmentsTableView.selectedSegmentIDs())
    self.moveCurrentToOtherButton.enabled = valid and len(self.currentSegmentsTableView.selectedSegmentIDs())
    self.moveOtherToCurrentButton.enabled = valid and len(self.otherSegmentsTableView.selectedSegmentIDs())
    self.currentSegmentsTableView.SegmentsTableMessageLabel.hide()
    self.otherSegmentsTableView.SegmentsTableMessageLabel.hide()

  def _copySegmentsBetweenSegmentations(self, copyFromCurrentSegmentation, removeFromSource):
    self.invokeEvent(self.StartedEvent)
    currentSegmentationNode = self.currentSegmentationNodeSelector.currentNode()
    otherSegmentationNode = self.otherSegmentationNodeSelector.currentNode()

    if not (currentSegmentationNode and otherSegmentationNode):
      logging.info("Current and other segmentation node needs to be selected")
      self.invokeEvent(self.FailedEvent)
      return

    if copyFromCurrentSegmentation:
      sourceSegmentation = currentSegmentationNode.GetSegmentation()
      targetSegmentation = otherSegmentationNode.GetSegmentation()
      otherSegmentationNode.CreateDefaultDisplayNodes()
      selectedSegmentIds = self.currentSegmentsTableView.selectedSegmentIDs()
    else:
      sourceSegmentation = otherSegmentationNode.GetSegmentation()
      targetSegmentation = currentSegmentationNode.GetSegmentation()
      currentSegmentationNode.CreateDefaultDisplayNodes()
      selectedSegmentIds = self.otherSegmentsTableView.selectedSegmentIDs()

    if not len(selectedSegmentIds):
      logging.warn("No segments are selected")
      self.invokeEvent(self.FailedEvent)
      return

    for segmentID in selectedSegmentIds:
      if not targetSegmentation.CopySegmentFromSegmentation(sourceSegmentation, segmentID, removeFromSource):
        self.invokeEvent(self.FailedEvent)
        raise RuntimeError("Segment %s could not be copied from segmentation %s tp %s " %(segmentID,
                                                                                          sourceSegmentation.GetName(),
                                                                                          targetSegmentation.GetName()))
    return self.invokeEvent(self.SuccessEvent)


class ImportLabelMapIntoSegmentationWidget(ImportIntoSegmentationWidgetBase):
  """ This widget provides functionality for importing from a labelmap into a segmentation

  .. code-block:: python

    from SlicerDevelopmentToolboxUtils.widgets import ImportLabelMapIntoSegmentationWidget

    w = ImportLabelMapIntoSegmentationWidget()
    w.segmentationNodeSelectorVisible = False

    w.show()

  """

  CanceledEvent = SlicerDevelopmentToolboxEvents.CanceledEvent

  _LayoutClass = qt.QFormLayout

  def __init__(self, parent=None):
    super(ImportLabelMapIntoSegmentationWidget, self).__init__(parent)
    self.volumesLogic = slicer.modules.volumes.logic()

  def setup(self):
    super(ImportLabelMapIntoSegmentationWidget, self).setup()

    self.segmentationLabel = qt.QLabel("Destination segmentation")
    self.labelMapSelector = self.createComboBox(nodeTypes=["vtkMRMLLabelMapVolumeNode", ""], showChildNodeTypes=False,
                                                addEnabled=False, removeEnabled=False, noneEnabled=True,
                                                selectNodeUponCreation=False, toolTip="Select labelmap to import from")

    self.importButton = self.createButton("Import", enabled=False)

    self.layout().addRow(self.segmentationLabel, self.segmentationNodeSelector)
    self.layout().addRow(qt.QLabel("Input labelmap:"), self.labelMapSelector)
    self.layout().addRow(self.importButton)

  def _setupConnections(self):
    self.segmentationNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)',
                                          lambda node: self._updateButtonAvailability())
    self.labelMapSelector.connect('currentNodeChanged(vtkMRMLNode*)', lambda node: self._updateButtonAvailability())
    self.importButton.clicked.connect(self._onImportButtonClicked)

  def _updateButtonAvailability(self):
    self.importButton.setEnabled(self.labelMapSelector.currentNode() and self.segmentationNodeSelector.currentNode())

  def _onImportButtonClicked(self):
    self.invokeEvent(self.StartedEvent)
    currentSegmentationNode = self.segmentationNodeSelector.currentNode()
    labelmapNode = self.labelMapSelector.currentNode()

    logging.debug("Starting import labelmap %s into segmentation %s" %(labelmapNode.GetName(),
                                                                       currentSegmentationNode.GetName()))

    masterVolume = ModuleLogicMixin.getReferencedVolumeFromSegmentationNode(currentSegmentationNode)

    if not masterVolume:
      raise ValueError("No referenced master volume found for %s" % currentSegmentationNode.GetName())

    warnings = self.volumesLogic.CheckForLabelVolumeValidity(masterVolume, labelmapNode)
    if warnings != "":
      if slicer.util.confirmYesNoDisplay("Geometry of master and label do not match. Do you want to resample the "
                                         "label?", detailedText=warnings):
        outputLabel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        outputLabel.SetName(labelmapNode.GetName() + "_resampled")
        ModuleLogicMixin.runBRAINSResample(inputVolume=labelmapNode, referenceVolume=masterVolume,
                                           outputVolume=outputLabel)
        labelmapNode = outputLabel
        self.labelMapSelector.setCurrentNode(outputLabel)
      else:
        self.invokeEvent(self.CanceledEvent)
        return

    currentSegmentationNode.CreateDefaultDisplayNodes()

    segmentationsLogic = slicer.modules.segmentations.logic()

    slicer.app.setOverrideCursor(qt.QCursor(qt.Qt.BusyCursor))
    success = segmentationsLogic.ImportLabelmapToSegmentationNode(labelmapNode, currentSegmentationNode)
    slicer.app.restoreOverrideCursor()

    if not success:
      message = "Failed to copy labels from labelmap volume node %s!" % labelmapNode.GetName()
      logging.error(message)

      slicer.util.warningDisplay("Failed to import from labelmap volume")
      self.invokeEvent(self.FailedEvent)
      return

    self.invokeEvent(self.SuccessEvent)


class SliceWidgetMessageBoxBase(qt.QMessageBox, ModuleWidgetMixin):
  """ This class represents the base of a slice widget based message box

    .. code-block:: python

      from SlicerDevelopmentToolboxUtils.widgets import SliceWidgetMessageBoxBase

      w = SliceWidgetMessageBoxBase("Red")
      w.exec_()
  """

  def __init__(self, widgetName, text="", parent=None, **kwargs):
    qt.QMessageBox.__init__(self, parent if parent else slicer.util.mainWindow())
    self.widgetName = widgetName
    self.text = text
    for key, value in kwargs.iteritems():
      if hasattr(self, key):
        setattr(self, key, value)
    self.setup()

  def setup(self):
    widget = self.layoutManager.sliceWidget(self.widgetName)
    if not widget:
      raise AttributeError("Slice widget with name %s not found" %self.widgetName)
    sliceNode = widget.sliceLogic().GetSliceNode()

    self.sliceWidget = slicer.qMRMLSliceWidget()
    self.sliceWidget.setMRMLScene(widget.mrmlScene())
    self.sliceWidget.setMRMLSliceNode(sliceNode)

    self.layout().addWidget(self.sliceWidget, 0, 1)
    self.layout().addWidget(qt.QLabel(self.text), 1 ,1)
    self.layout().addWidget(self.createHLayout(self.buttons()), 2, 1)

  def exec_(self):
    raise NotImplementedError


class SliceWidgetConfirmYesNoMessageBox(SliceWidgetMessageBoxBase):
  """ SliceWidgetConfirmYesNoMessageBox for displaying a slice widget with a specific question to confirm

    .. code-block:: python

      from SlicerDevelopmentToolboxUtils.widgets import SliceWidgetConfirmYesNoMessageBox

      w = SliceWidgetConfirmYesNoMessageBox("Red", "Some random text")
      w.exec_()
  """

  def __init__(self, widgetName, text="", parent=None, **kwargs):
    super(SliceWidgetConfirmYesNoMessageBox, self).__init__(widgetName, text, parent,
                                                            standardButtons=qt.QMessageBox.Yes | qt.QMessageBox.No |
                                                                            qt.QMessageBox.Cancel, **kwargs)

  def exec_(self):
    widget = self.layoutManager.sliceWidget(self.widgetName)
    self.sliceWidget.setFixedSize(widget.size)
    return qt.QMessageBox.exec_(self)


class RadioButtonChoiceMessageBox(qt.QMessageBox, ModuleWidgetMixin):
  """ MessageBox for displaying a message box giving the user a choice between different options.

    .. code-block:: python

      from SlicerDevelopmentToolboxUtils.widgets import RadioButtonChoiceMessageBox

      mbox = RadioButtonChoiceMessageBox("Question?", options=["a", "b"])
      mbox.exec_()
  """
  def __init__(self, text, options, *args):
    assert type(options) in [list, tuple] and len(options) > 1, "Valid types of 'options' are: list or tuple and needs" \
                                                                "to have at least two options"
    qt.QMessageBox.__init__(self, *args)
    self.standardButtons = qt.QMessageBox.Ok | qt.QMessageBox.Cancel
    self.text = text
    self.options = options
    self._setup()

  def __del__(self):
    super(RadioButtonChoiceMessageBox, self).__del__()
    for button in self.buttonGroup.buttons():
      self._disconnectButton(button)

  def show(self):
    return self.exec_()

  def reject(self):
    qt.QMessageBox.reject(self)

  def closeEvent(self, event):
    qt.QMessageBox.closeEvent(self, event)
    self.reject()

  def exec_(self):
    self.selectedOption = None
    self.button(qt.QMessageBox.Ok).enabled = False
    for b in self.buttonGroup.buttons():
      self.buttonGroup.setExclusive(False)
      b.checked = False
      self.buttonGroup.setExclusive(True)
    result = qt.QMessageBox.exec_(self)
    if result == qt.QMessageBox.Ok:
      return self.selectedOption
    return None

  def _setup(self):
    self.buttonGroup = qt.QButtonGroup()
    for optionId, option in enumerate(self.options):
      button = self.createRadioButton(option)
      button.setProperty('value', option)
      button.setCursor(qt.Qt.PointingHandCursor)
      self._connectButton(button)
      self.buttonGroup.addButton(button, optionId)
    col = self.createVLayout(list(self.buttonGroup.buttons()))
    self.layout().addWidget(col, 1, 1)

  def _connectButton(self, button):
    button.clicked.connect(lambda: self._onOptionSelected(button.value))

  def _disconnectButton(self, button):
    button.clicked.disconnect(lambda: self._onOptionSelected(button.value))

  def _onOptionSelected(self, value):
    self.selectedOption = value
    self.button(qt.QMessageBox.Ok).enabled = True
