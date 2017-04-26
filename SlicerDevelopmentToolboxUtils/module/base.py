import os
import logging
import vtk
import qt

import slicer


from ..mixins import GeneralModuleMixin, ModuleWidgetMixin
from ..decorators import onModuleSelected


class ModuleBase(GeneralModuleMixin):

  MODULE_NAME = None

  @property
  def resourcesPath(self):
    return os.path.join(self.modulePath, "Resources")

  def __init__(self):
    if not self.MODULE_NAME:
      raise NotImplementedError("Member MODULE_NAME needs to be defined in order to get the module path and resources")
    self.modulePath = self.getModulePath()
    self.addMrmlSceneClearObserver()

  def __del__(self):
    super(ModuleBase, self).__del__()
    self.cleanup()

  def addMrmlSceneClearObserver(self):

    @onModuleSelected(self.MODULE_NAME)
    def onMrmlSceneCleared(caller, event):
      logging.debug("called onMrmlSceneCleared in %s" % self.__class__.__name__)
      self.onMrmlSceneCleared(caller, event)

    self.mrmlSceneObserver = slicer.mrmlScene.AddObserver(slicer.mrmlScene.EndCloseEvent, onMrmlSceneCleared)

  def onMrmlSceneCleared(self, caller, event):
    pass

  def cleanup(self):
    if self.mrmlSceneObserver:
      self.mrmlSceneObserver = slicer.mrmlScene.RemoveObserver(self.mrmlSceneObserver)

  def getModulePath(self):
    return os.path.dirname(slicer.util.modulePath(self.MODULE_NAME))

  def getSetting(self, setting, moduleName=None, default=None):
    return GeneralModuleMixin.getSetting(self, setting, moduleName=moduleName if moduleName else self.MODULE_NAME,
                                         default=default)

  def setSetting(self, setting, value, moduleName=None):
    return GeneralModuleMixin.setSetting(self, setting, value,
                                         moduleName=moduleName if moduleName else self.MODULE_NAME)


class SessionBasedModuleBase(ModuleBase):

  SessionClass = None

  def __init__(self):
    super(SessionBasedModuleBase, self).__init__()
    if not self.SessionClass:
      raise NotImplementedError("Member SessionClass needs to be defined.")
    self.session = self.SessionClass()


class WidgetBase(qt.QWidget, SessionBasedModuleBase, ModuleWidgetMixin):

  NAME = None

  ActivatedEvent = vtk.vtkCommand.UserEvent + 150
  DeactivatedEvent = vtk.vtkCommand.UserEvent + 151

  LogicClass = None
  LayoutClass = qt.QGridLayout

  @property
  def currentResult(self):
    return self.session.currentResult

  @currentResult.setter
  def currentResult(self, value):
    self.session.currentResult = value

  @property
  def active(self):
    self._activated = getattr(self, "_activated", False)
    return self._activated

  @active.setter
  def active(self, value):
    if self.active == value:
      return
    self._activated = value
    logging.debug("%s %s" % ("activated" if self.active else "deactivate", self.NAME))
    self.invokeEvent(self.ActivatedEvent if self.active else self.DeactivatedEvent)
    if self.active:
      self.onActivation()
    else:
      self.onDeactivation()

  def __init__(self):
    qt.QWidget.__init__(self)
    SessionBasedModuleBase.__init__(self)
    if not self.NAME:
      raise NotImplementedError("NAME needs to be defined for each widget based class")
    self._plugins = []
    if self.LogicClass:
      self.logic = self.LogicClass()
    self.setLayout(self.LayoutClass())
    self.setupIcons()
    self.setup()
    self.setupSessionObservers()
    self.setupConnections()

  def __del__(self):
    self.removeSessionEventObservers()

  def setupIcons(self):
    pass

  def setup(self):
    NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def setupConnections(self):
    NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def setupSessionObservers(self):
    self.session.addEventObserver(self.session.NewCaseStartedEvent, self.onNewCaseStarted)
    self.session.addEventObserver(self.session.CaseOpenedEvent, self.onCaseOpened)
    self.session.addEventObserver(self.session.CloseCaseEvent, self.onCaseClosed)

  def removeSessionEventObservers(self):
    self.session.removeEventObserver(self.session.NewCaseStartedEvent, self.onNewCaseStarted)
    self.session.removeEventObserver(self.session.CaseOpenedEvent, self.onCaseOpened)
    self.session.removeEventObserver(self.session.CloseCaseEvent, self.onCaseClosed)

  def onActivation(self):
    self._activatePlugins()

  def onDeactivation(self):
    self._deactivatePlugins()

  def onNewCaseStarted(self, caller, event):
    pass

  def onCaseOpened(self, caller, event):
    pass

  @vtk.calldata_type(vtk.VTK_STRING)
  def onCaseClosed(self, caller, event, callData):
    pass

  def _activatePlugins(self):
    self.__setPluginsActivated(True)

  def _deactivatePlugins(self):
    self.__setPluginsActivated(False)

  def __setPluginsActivated(self, activated):
    for plugin in self._plugins:
      plugin.active = activated

  def addPlugin(self, plugin):
    assert hasattr(plugin, "active"), "Plugin needs to be a subclass of %s" % SliceTrackerPlugin.__class__.__name__
    self._plugins.append(plugin)