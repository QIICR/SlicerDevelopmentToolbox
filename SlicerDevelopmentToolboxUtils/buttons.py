import inspect
import os
import vtk
import qt
import slicer
from helpers import WindowLevelEffect
from events import SlicerDevelopmentToolboxEvents
from mixins import ParameterNodeObservationMixin, ModuleWidgetMixin
from widgets import SettingsMessageBox


class BasicIconButton(qt.QPushButton):
  """ Base class for icon based qt.QPushButton

  Args:
    text (str, optional): text to be displayed for the button
    parent (qt.QWidget, optional): parent of the button
  """

  _ICON_FILENAME=None

  @property
  def _buttonIcon(self):
    if not self._ICON_FILENAME:
      raise ValueError("_ICON_FILENAME needs to be defined by subclasses")
    iconPath = os.path.join(os.path.dirname(inspect.getfile(self.__class__)), '../Resources/Icons', self._ICON_FILENAME)
    pixmap = qt.QPixmap(iconPath)
    return qt.QIcon(pixmap)

  def __init__(self, text="", parent=None, **kwargs):
    qt.QPushButton.__init__(self, text, parent, **kwargs)
    self.setIcon(self._buttonIcon)
    self._connectSignals()

  def _connectSignals(self):
    self.destroyed.connect(self._onAboutToBeDestroyed)

  def _onAboutToBeDestroyed(self, obj):
    obj.destroyed.disconnect(self._onAboutToBeDestroyed)


class CheckableIconButton(BasicIconButton):
  """ Base class for icon based checkable qt.QPushButton. Needs to implement method 'onToggled'

  Args:
    text (str, optional): text to be displayed for the button
    parent (qt.QWidget, optional): parent of the button
  """

  def __init__(self, text="", parent=None, **kwargs):
    BasicIconButton.__init__(self, text, parent, **kwargs)
    self.checkable = True

  def _connectSignals(self):
    super(CheckableIconButton, self)._connectSignals()
    self.toggled.connect(self._onToggled)

  def _onToggled(self, checked):
    raise NotImplementedError()


class ModuleSettingsButton(BasicIconButton):
  """ qt.QPushButton that upon click displays the qt.QSettings() for the delivered moduleName in a separate dialog

  Args:
    moduleName (str): Name of the module whose settings you want to see (modify).
    text (str, optional): text to be displayed for the button
  """

  _ICON_FILENAME = 'icon-settings.png'

  def __init__(self, moduleName, text="", parent=None, **kwargs):
    self.moduleName = moduleName
    super(ModuleSettingsButton, self).__init__(text, parent, **kwargs)

  def _connectSignals(self):
    super(ModuleSettingsButton, self)._connectSignals()
    self.clicked.connect(self.__onClicked)

  def __onClicked(self):
    settings = SettingsMessageBox(self.moduleName, slicer.util.mainWindow())
    settings.show()


class LayoutButton(CheckableIconButton):
  """ Base class for layout specific buttons

  LayoutButton can be subclassed where each subclass needs to define a layout. Once the button is pushed, 3D Slicer
  switches to the defined layout. LayoutButton is connected to layout changes signal which means that upon layout
  changes LayoutButton checks itself if the new layout matches the layout its defined layout and checks or unchecks
  itself.

  Args:
    text (str, optional): text to be displayed for the button
    parent (qt.QWidget, optional): parent of the button

  Note:
    Subclasses need to define class member 'LAYOUT'. Available layouts are listed on the referenced page.

  See also:
    http://apidocs.slicer.org/master/classvtkMRMLLayoutNode.html

  """

  LAYOUT=None

  @property
  def layoutManager(self):
    """ Returns 3D Slicer layout manager

    Returns:
       slicer.app.layoutManager()
    """
    return slicer.app.layoutManager()

  def __init__(self, text="", parent=None, **kwargs):
    super(LayoutButton, self).__init__(text, parent, **kwargs)
    if not self.LAYOUT:
      raise NotImplementedError("Member variable LAYOUT needs to be defined by all deriving classes")
    self._onLayoutChanged(self.layoutManager.layout)

  def _connectSignals(self):
    super(LayoutButton, self)._connectSignals()
    self.layoutManager.layoutChanged.connect(self._onLayoutChanged)

  def _onAboutToBeDestroyed(self, obj):
    super(LayoutButton, self)._onAboutToBeDestroyed(obj)
    if self.layoutManager:
      self.layoutManager.layoutChanged.disconnect(self._onLayoutChanged)

  def _onLayoutChanged(self, layout):
    self.checked = self.LAYOUT == layout

  def _onToggled(self, checked):
    if checked and self.layoutManager.layout != self.LAYOUT:
      self.layoutManager.setLayout(self.LAYOUT)
    if not checked and self.LAYOUT == self.layoutManager.layout:
      self._onLayoutChanged(self.LAYOUT)


class RedSliceLayoutButton(LayoutButton):
  """ LayoutButton inherited class which represents a button for the SlicerLayoutOneUpRedSliceView including the icon.

  Args:
    text (str, optional): text to be displayed for the button
    parent (qt.QWidget, optional): parent of the button
  """

  _ICON_FILENAME = 'LayoutOneUpRedSliceView.png'
  LAYOUT = slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView

  def __init__(self, text="", parent=None, **kwargs):
    super(RedSliceLayoutButton, self).__init__(text, parent, **kwargs)
    self.toolTip = "Red Slice Only Layout"


class FourUpLayoutButton(LayoutButton):
  """ LayoutButton inherited class which represents a button for the SlicerLayoutFourUpView including the icon.

  Args:
    text (str, optional): text to be displayed for the button
    parent (qt.QWidget, optional): parent of the button
  """

  _ICON_FILENAME = 'LayoutFourUpView.png'
  LAYOUT = slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView

  def __init__(self, text="", parent=None, **kwargs):
    super(FourUpLayoutButton, self).__init__(text, parent, **kwargs)
    self.toolTip = "Four-Up Layout"


class FourUpTableViewLayoutButton(LayoutButton):
  """ LayoutButton inherited class which represents a button for the SlicerLayoutFourUpTableView including the icon.

  Args:
    text (str, optional): text to be displayed for the button
    parent (qt.QWidget, optional): parent of the button
  """

  _ICON_FILENAME = 'LayoutFourUpTableView.png'
  LAYOUT = slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpTableView

  def __init__(self, text="", parent=None, **kwargs):
    super(FourUpTableViewLayoutButton, self).__init__(text, parent, **kwargs)
    self.toolTip = "Four-Up Table Layout"


class SideBySideLayoutButton(LayoutButton):
  """ LayoutButton inherited class which represents a button for the SlicerLayoutSideBySideView including the icon.

  Args:
    text (str, optional): text to be displayed for the button
    parent (qt.QWidget, optional): parent of the button
  """

  _ICON_FILENAME = 'LayoutSideBySideView.png'
  LAYOUT = slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView

  def __init__(self, text="", parent=None, **kwargs):
    super(SideBySideLayoutButton, self).__init__(text, parent, **kwargs)
    self.toolTip = "Side by Side Layout"


class CrosshairButton(CheckableIconButton, ParameterNodeObservationMixin):
  """ Represents a button for enabling/disabling crosshair for better slice view coordination.

  Args:
    text (str, optional): text to be displayed for the button
    parent (qt.QWidget, optional): parent of the button

  Attributes:
    CursorPositionModifiedEvent (slicer.vtkMRMLCrosshairNode.CursorPositionModifiedEvent)
    _DEFAULT_CROSSHAIR_MODE (enum): defining the crosshair display mode (see referenced web page)

  See Also: http://apidocs.slicer.org/master/classvtkMRMLCrosshairNode.html

  """

  _ICON_FILENAME = 'SlicesCrosshair.png'
  CursorPositionModifiedEvent = SlicerDevelopmentToolboxEvents.CursorPositionModifiedEvent
  _DEFAULT_CROSSHAIR_MODE = slicer.vtkMRMLCrosshairNode.ShowSmallBasic

  @property
  def crosshairMode(self):
    return self._crosshairMode

  @crosshairMode.setter
  def crosshairMode(self, mode):
    if not type(mode) is int:
      raise ValueError("Mode seems not to be valid")
    self._crosshairMode = mode
    self.crosshairNode.SetCrosshairMode(mode)

  def __init__(self, text="", parent=None, **kwargs):
    super(CrosshairButton, self).__init__(text, parent, **kwargs)
    self.toolTip = "Display crosshair"
    self.crosshairNodeObserverTag = None
    self.crosshairNode = slicer.mrmlScene.GetNthNodeByClass(0, 'vtkMRMLCrosshairNode')
    self.crosshairNodeModifiedObserver = self.crosshairNode.AddObserver(vtk.vtkCommand.ModifiedEvent,
                                                                        self._onCrosshairNodeModified)
    self._crosshairMode = self._DEFAULT_CROSSHAIR_MODE
    self.sliceIntersectionEnabled = False

  def _onAboutToBeDestroyed(self, obj):
    super(CrosshairButton, self)._onAboutToBeDestroyed(obj)
    self._disconnectCrosshairNode()
    if self.crosshairNode and self.crosshairNodeModifiedObserver:
      self.crosshairNodeModifiedObserver = self.crosshairNode.RemoveObserver(self.crosshairNodeModifiedObserver)

  def setSliceIntersectionEnabled(self, enabled):
    self.sliceIntersectionEnabled = enabled

  def _onCrosshairNodeModified(self, caller, event):
    mode = self.crosshairNode.GetCrosshairMode()
    self.checked = not mode is slicer.vtkMRMLCrosshairNode.NoCrosshair

  def _onToggled(self, checked):
    if checked:
      self._connectCrosshairNode()
    else:
      self._disconnectCrosshairNode()

  def _connectCrosshairNode(self):
    if not self.crosshairNodeObserverTag:
      self.crosshairNodeObserverTag = self.crosshairNode.AddObserver(self.CursorPositionModifiedEvent,
                                                                     self._onCursorPositionChanged)
    self.crosshairNode.SetCrosshairMode(self.crosshairMode)
    self._showSliceIntersection(self.sliceIntersectionEnabled)

  def _onCursorPositionChanged(self, observee=None, event=None):
    self.invokeEvent(self.CursorPositionModifiedEvent, self.crosshairNode)

  def _disconnectCrosshairNode(self):
    if self.crosshairNode and self.crosshairNodeObserverTag:
      self.crosshairNode.RemoveObserver(self.crosshairNodeObserverTag)
    self.crosshairNodeObserverTag = None
    self.crosshairNode.SetCrosshairMode(slicer.vtkMRMLCrosshairNode.NoCrosshair)
    self._showSliceIntersection(False)

  def _showSliceIntersection(self, show):
    viewNodes = slicer.mrmlScene.GetNodesByClass('vtkMRMLSliceCompositeNode')
    viewNodes.UnRegister(slicer.mrmlScene)
    viewNodes.InitTraversal()
    viewNode = viewNodes.GetNextItemAsObject()
    while viewNode:
      viewNode.SetSliceIntersectionVisibility(show)
      viewNode = viewNodes.GetNextItemAsObject()


class WindowLevelEffectsButton(CheckableIconButton, ModuleWidgetMixin):
  """ WindowLevelEffectsButton adds the possibility to change W/L once it is checked.

  Change W/L (with respect to foreground and background opacity) by moving the cursor while pushing and holding the
  left mouse button over a 3D Slicer qMRMLSliceWidget.

  Args:
    text (str, optional): text to be displayed for the button
    sliceWidgets (list, optional): list of qMRMLSliceWidget
    parent (qt.QWidget, optional): parent of the button

  Note: If no sliceWidgets has been specified while instantiation, all visible qMRMLSliceWidget will be observed and
  on layout changes updated.
  """

  _ICON_FILENAME = 'icon-WindowLevelEffect.png'

  @property
  def sliceWidgets(self):
    """ List of qMRMLSliceWidget
    """
    if not self._sliceWidgets:
      self._sliceWidgets = list(ModuleWidgetMixin.getAllVisibleWidgets())
    return self._sliceWidgets

  @sliceWidgets.setter
  def sliceWidgets(self, sliceWidgets):
    self._sliceWidgets = sliceWidgets
    self._setup()

  def __init__(self, text="", sliceWidgets=None, parent=None, **kwargs):
    super(WindowLevelEffectsButton, self).__init__(text, parent, **kwargs)
    self.toolTip = "Change W/L with respect to FG and BG opacity"
    self._wlEffects = {}
    self.sliceWidgets = sliceWidgets
    self.layoutManager.layoutChanged.connect(self._onLayoutChanged)
    self._refreshOnLayoutChanged = sliceWidgets is None

  def _onAboutToBeDestroyed(self, obj):
    CheckableIconButton._onAboutToBeDestroyed(self, obj)
    if self.layoutManager:
      self.layoutManager.layoutChanged.disconnect(self._onLayoutChanged)

  def refreshForAllAvailableSliceWidgets(self):
    """ Refreshs the the WindowLevelEffectsButton to work on all visible qMRMLSliceWidget
    """
    self.sliceWidgets = None

  def setRefreshOnLayoutChanged(self, enabled):
    """ Control if WindowLevelEffect should be updated on layout changes.

    If this option is activated, every time the layout changes, the WindowLevelEffects will observe and operate on all
    visible qMRMLSliceWidgets.

    Args:
      enabled (bool): specifying if WindowLevelEffect should be updated on layout changes
    """
    self._refreshOnLayoutChanged = enabled

  def _setup(self):
    self._cleanupSliceWidgets()
    for sliceWidget in self.sliceWidgets :
      self.addSliceWidget(sliceWidget)

  def _cleanupSliceWidgets(self):
    for sliceWidget in self._wlEffects.keys():
      if sliceWidget not in self.sliceWidgets:
        self.removeSliceWidget(sliceWidget)

  def addSliceWidget(self, sliceWidget):
    """ Add qMRMLSliceWidget to the list of qMRMLSliceWidget and create a new WindowLevelEffect for it

    Args:
      sliceWidget(qMRMLSliceWidget): qMRMLSliceWidget to be added to the list of observed qMRMLSliceWidgets
    See Also: http://apidocs.slicer.org/master/classqMRMLSliceWidget.html
    """
    if not self._wlEffects.has_key(sliceWidget):
      self._wlEffects[sliceWidget] = WindowLevelEffect(sliceWidget)

  def removeSliceWidget(self, sliceWidget):
    """ Removes a qMRMLSliceWidget from the list of observed qMRMLSliceWidgets

    Args:
      sliceWidget(qMRMLSliceWidget): qMRMLSliceWidget to be removed to the list of observed qMRMLSliceWidgets
    See Also: http://apidocs.slicer.org/master/classqMRMLSliceWidget.html
    """
    if self._wlEffects.has_key(sliceWidget):
      self._wlEffects[sliceWidget].disable()
      del self._wlEffects[sliceWidget]

  def _onLayoutChanged(self, layout):
    if self._refreshOnLayoutChanged:
      self.refreshForAllAvailableSliceWidgets()
      if self.checked:
        self._enableWindowLevelEffects()

  def _onToggled(self, checked):
    self._enableWindowLevelEffects() if checked else self._disableWindowLevelEffects()

  def _enableWindowLevelEffects(self):
    for wlEffect in self._wlEffects.values():
      wlEffect.enable()

  def _disableWindowLevelEffects(self):
    for wlEffect in self._wlEffects.values():
      wlEffect.disable()


