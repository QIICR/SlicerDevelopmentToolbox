import slicer
from slicer.ScriptedLoadableModule import *
import SlicerDevelopmentToolboxUtils


class SlicerDevelopmentToolboxClass(object):

  def __init__(self):
    pass


class SlicerDevelopmentToolbox(ScriptedLoadableModule):
  """
  This class is the 'hook' for slicer to detect and recognize the plugin
  as a loadable scripted module
  """
  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    parent.title = "SlicerDevelopmentToolbox Utils"
    parent.categories = ["Developer Tools.Utils"]
    parent.hidden = True
    parent.contributors = ["Christian Herz (SPL), Andrey Fedorov (SPL)"]
    parent.helpText = """
    This class represents a hidden module which includes a lot of useful
    helpers, constants, decorators and mixins.
    No module interface here.
    """
    parent.acknowledgementText = """
    These SlicerDevelopmentToolbox utils were developed by
    Christian Herz, SPL
    """

    slicer.modules.slicerSDT = SlicerDevelopmentToolboxClass