from .base import SessionBasedModuleBase, ModuleBase
from ..mixins import ModuleLogicMixin


class LogicBase(ModuleBase, ModuleLogicMixin):

  def __init__(self):
    ModuleBase.__init__(self)


class SessionBasedLogicBase(SessionBasedModuleBase, ModuleLogicMixin):

  SessionClass = None

  def __init__(self):
    SessionBasedModuleBase.__init__(self)