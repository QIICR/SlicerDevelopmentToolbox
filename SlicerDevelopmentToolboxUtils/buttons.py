import inspect
import os

import qt
import slicer
from helpers import WindowLevelEffect
from events import SlicerDevelopmentToolboxEvents
from mixins import ParameterNodeObservationMixin
from widgets import SettingsMessageBox


class BasicIconButton(qt.QPushButton):

  ICON_FILENAME=None

  @property
  def buttonIcon(self):
    if not self.ICON_FILENAME:
      return None
    iconPath = os.path.join(os.path.dirname(inspect.getfile(self.__class__)), '../Resources/Icons', self.ICON_FILENAME)
    pixmap = qt.QPixmap(iconPath)
    return qt.QIcon(pixmap)

  def __init__(self, title="", parent=None, **kwargs):
    qt.QPushButton.__init__(self, title, parent, **kwargs)
    self.setIcon(self.buttonIcon)
    self._connectSignals()

  def _connectSignals(self):
    self.destroyed.connect(self.onAboutToBeDestroyed)

  def onAboutToBeDestroyed(self, obj):
    obj.destroyed.disconnect(self.onAboutToBeDestroyed)


class CheckableIconButton(BasicIconButton):

  def __init__(self, title="", parent=None, **kwargs):
    BasicIconButton.__init__(self, title, parent, **kwargs)
    self.checkable = True

  def _connectSignals(self):
    super(CheckableIconButton, self)._connectSignals()
    self.toggled.connect(self.onToggled)

  def onToggled(self, checked):
    raise NotImplementedError()


class ModuleSettingsButton(BasicIconButton):

  ICON_FILENAME = 'icon-settings.png'

  def __init__(self, moduleName, title="", parent=None, **kwargs):
    self.moduleName = moduleName
    super(ModuleSettingsButton, self).__init__(title, parent, **kwargs)

  def _connectSignals(self):
    super(ModuleSettingsButton, self)._connectSignals()
    self.clicked.connect(self.onClicked)

  def onClicked(self):
    settings = SettingsMessageBox(self.moduleName, slicer.util.mainWindow())
    settings.show()


class LayoutButton(CheckableIconButton):

  LAYOUT=None

  @property
  def layoutManager(self):
    return slicer.app.layoutManager()

  def __init__(self, title="", parent=None, **kwargs):
    super(LayoutButton, self).__init__(title, parent, **kwargs)
    if not self.LAYOUT:
      raise NotImplementedError("Member variable LAYOUT needs to be defined by all deriving classes")
    self.onLayoutChanged(self.layoutManager.layout)

  def _connectSignals(self):
    super(LayoutButton, self)._connectSignals()
    self.layoutManager.layoutChanged.connect(self.onLayoutChanged)

  def onAboutToBeDestroyed(self, obj):
    super(LayoutButton, self).onAboutToBeDestroyed(obj)
    if self.layoutManager:
      self.layoutManager.layoutChanged.disconnect(self.onLayoutChanged)

  def onLayoutChanged(self, layout):
    self.checked = self.LAYOUT == layout

  def onToggled(self, checked):
    if checked and self.layoutManager.layout != self.LAYOUT:
      self.layoutManager.setLayout(self.LAYOUT)
    if not checked and self.LAYOUT == self.layoutManager.layout:
      self.onLayoutChanged(self.LAYOUT)


class RedSliceLayoutButton(LayoutButton):

  ICON_FILENAME = 'LayoutOneUpRedSliceView.png'
  LAYOUT = slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView

  def __init__(self, title="", parent=None, **kwargs):
    super(RedSliceLayoutButton, self).__init__(title, parent, **kwargs)
    self.toolTip = "Red Slice Only Layout"


class FourUpLayoutButton(LayoutButton):

  ICON_FILENAME = 'LayoutFourUpView.png'
  LAYOUT = slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView

  def __init__(self, title="", parent=None, **kwargs):
    super(FourUpLayoutButton, self).__init__(title, parent, **kwargs)
    self.toolTip = "Four-Up Layout"


class FourUpTableViewLayoutButton(LayoutButton):

  ICON_FILENAME = 'LayoutFourUpTableView.png'
  LAYOUT = slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpTableView

  def __init__(self, title="", parent=None, **kwargs):
    super(FourUpTableViewLayoutButton, self).__init__(title, parent, **kwargs)
    self.toolTip = "Four-Up Table Layout"


class SideBySideLayoutButton(LayoutButton):

  ICON_FILENAME = 'LayoutSideBySideView.png'
  LAYOUT = slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView

  def __init__(self, title="", parent=None, **kwargs):
    super(SideBySideLayoutButton, self).__init__(title, parent, **kwargs)
    self.toolTip = "Side by Side Layout"


class CrosshairButton(CheckableIconButton, ParameterNodeObservationMixin):

  ICON_FILENAME = 'SlicesCrosshair.png'
  CursorPositionModifiedEvent = SlicerDevelopmentToolboxEvents.CursorPositionModifiedEvent
  DEFAULT_CROSSHAIR_MODE = slicer.vtkMRMLCrosshairNode.ShowSmallBasic

  def __init__(self, title="", parent=None, **kwargs):
    super(CrosshairButton, self).__init__(title, parent, **kwargs)
    self.toolTip = "Show crosshair"
    self.crosshairNodeObserverTag = None
    self.crosshairNode = slicer.mrmlScene.GetNthNodeByClass(0, 'vtkMRMLCrosshairNode')
    self.crosshairMode = self.DEFAULT_CROSSHAIR_MODE
    self.sliceIntersectionEnabled = False

  def setCrosshairMode(self, mode):
    self.crosshairMode = mode

  def setSliceIntersectionEnabled(self, enabled):
    self.sliceIntersectionEnabled = enabled

  def onAboutToBeDestroyed(self, obj):
    super(CrosshairButton, self).onAboutToBeDestroyed(obj)
    self._disconnectCrosshairNode()

  def _connectCrosshairNode(self):
    if not self.crosshairNodeObserverTag:
      self.crosshairNodeObserverTag = self.crosshairNode.AddObserver(self.CursorPositionModifiedEvent,
                                                                     self.onCursorPositionChanged)

  def _disconnectCrosshairNode(self):
    if self.crosshairNode and self.crosshairNodeObserverTag:
      self.crosshairNode.RemoveObserver(self.crosshairNodeObserverTag)
    self.crosshairNodeObserverTag = None

  def onCursorPositionChanged(self, observee=None, event=None):
    self.invokeEvent(self.CursorPositionModifiedEvent, self.crosshairNode)

  def onToggled(self, checked):
    if checked:
      self._connectCrosshairNode()
      self.crosshairNode.SetCrosshairMode(self.crosshairMode)
      self._showSliceIntersection(self.sliceIntersectionEnabled)
    else:
      self._disconnectCrosshairNode()
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


class WindowLevelEffectsButton(CheckableIconButton):

  ICON_FILENAME = 'icon-WindowLevelEffect.png'

  @property
  def sliceWidgets(self):
    return self._sliceWidgets

  @sliceWidgets.setter
  def sliceWidgets(self, value):
    self._sliceWidgets = value
    self.setup()

  def __init__(self, title="", sliceWidgets=None, parent=None, **kwargs):
    super(WindowLevelEffectsButton, self).__init__(title, parent, **kwargs)
    self.toolTip = "Change W/L with respect to FG and BG opacity"
    self.wlEffects = {}
    self.sliceWidgets = sliceWidgets

  def refreshForAllAvailableSliceWidgets(self):
    self.sliceWidgets = None

  def setup(self):
    lm = slicer.app.layoutManager()
    if not self.sliceWidgets:
      self._sliceWidgets = []
      sliceLogics = lm.mrmlSliceLogics()
      for n in range(sliceLogics.GetNumberOfItems()):
        sliceLogic = sliceLogics.GetItemAsObject(n)
        self._sliceWidgets.append(lm.sliceWidget(sliceLogic.GetName()))
    for sliceWidget in self._sliceWidgets :
      self.addSliceWidget(sliceWidget)

  def cleanupSliceWidgets(self):
    for sliceWidget in self.wlEffects.keys():
      if sliceWidget not in self._sliceWidgets:
        self.removeSliceWidget(sliceWidget)

  def addSliceWidget(self, sliceWidget):
    if not self.wlEffects.has_key(sliceWidget):
      self.wlEffects[sliceWidget] = WindowLevelEffect(sliceWidget)

  def removeSliceWidget(self, sliceWidget):
    if self.wlEffects.has_key(sliceWidget):
      self.wlEffects[sliceWidget].disable()
      del self.wlEffects[sliceWidget]

  def onToggled(self, checked):
    self._enableWindowLevelEffects() if checked else self._disableWindowLevelEffects()


  def _enableWindowLevelEffects(self):
    for wlEffect in self.wlEffects.values():
      wlEffect.enable()

  def _disableWindowLevelEffects(self):
    for wlEffect in self.wlEffects.values():
      wlEffect.disable()


