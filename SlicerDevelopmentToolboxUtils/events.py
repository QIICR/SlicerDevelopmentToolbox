import vtk

class SlicerDevelopmentToolboxEvents(object):

  NewImageDataReceivedEvent = vtk.vtkCommand.UserEvent + 100
  NewFileIndexedEvent = vtk.vtkCommand.UserEvent + 101

  StartedEvent = vtk.vtkCommand.UserEvent + 201
  CanceledEvent = vtk.vtkCommand.UserEvent + 202
  SkippedEvent = vtk.vtkCommand.UserEvent + 203
  StoppedEvent = vtk.vtkCommand.UserEvent + 204
  FinishedEvent = vtk.vtkCommand.UserEvent + 205
  FailedEvent = vtk.vtkCommand.UserEvent + 206
  SuccessEvent = vtk.vtkCommand.UserEvent + 207

  FileCountChangedEvent = vtk.vtkCommand.UserEvent + 300
  StatusChangedEvent = vtk.vtkCommand.UserEvent + 301