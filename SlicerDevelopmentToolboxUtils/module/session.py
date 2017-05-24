import shutil
import os
import logging
import vtk
from abc import ABCMeta, abstractmethod

from ..mixins import ModuleLogicMixin
from .base import ModuleBase


class SessionBase(ModuleBase, ModuleLogicMixin):

  __metaclass__ = ABCMeta

  DirectoryChangedEvent = vtk.vtkCommand.UserEvent + 203

  NewCaseStartedEvent = vtk.vtkCommand.UserEvent + 501
  CloseCaseEvent = vtk.vtkCommand.UserEvent + 502
  CaseOpenedEvent = vtk.vtkCommand.UserEvent + 503

  @property
  def directory(self):
    self._directory = getattr(self, "_directory", None)
    return self._directory

  @directory.setter
  def directory(self, value):
    if value:
      if not os.path.exists(value):
        self.createDirectory(value)
    elif not value and self.directory:
      if self.getDirectorySize(self._directory) == 0:
        shutil.rmtree(self.directory)
    self._directory = value
    if self.directory:
      self.processDirectory()
    self.invokeEvent(self.DirectoryChangedEvent, self.directory)

  def __init__(self, *args, **kwargs):
    ModuleBase.__init__(self)
    self._steps = []

  @abstractmethod
  def load(self):
    pass

  @abstractmethod
  def processDirectory(self):
    pass

  @abstractmethod
  def save(self):
    pass


class StepBasedSession(SessionBase):

  @property
  def steps(self):
    return self._steps

  @steps.setter
  def steps(self, value):
    for step in self.steps:
      step.removeSessionEventObservers()
    self._steps = value

  def __init__(self):
    super(StepBasedSession, self).__init__()

  def registerStep(self, step):
    logging.debug("Registering step %s" % step.NAME)
    if step not in self.steps:
      self.steps.append(step)

  def getStep(self, stepName):
    return next((x for x in self.steps if x.NAME == stepName), None)