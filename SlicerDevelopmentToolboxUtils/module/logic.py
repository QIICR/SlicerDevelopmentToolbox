from .base import SessionBasedModuleBase
from ..mixins import ModuleLogicMixin


class LogicBase(SessionBasedModuleBase, ModuleLogicMixin):

  SessionClass = None

  def __init__(self):
    SessionBasedModuleBase.__init__(self)