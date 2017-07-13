import os
import inspect
import qt
import re
from decorators import classproperty


class IconsMetaClass(type):
  """ IconMetaClass searches the Resources/Icons directory for png files starting with 'icon-' and provides class members

  No code needs to be changed when adding a new icon. The filename of the icon should look as follows:
  'icon-'...'.png'. Capital letters will be transformed to lower case and '-' and ' ' will be replaced with '_'

  Examples:
    icon-fiducial-add.png --> Icons.fiducial_add

    icon-cursor-WindowLevel.png --> Icons.cursor_window_level

    icon-layout-OneUpRedSliceView.png --> Icons.layout_one_up_red_slice_view

  Note:
    This class is used as a metaclass
  """

  @classproperty
  def _getDictionaryFromDirectory(cls):
    modulePath = os.path.dirname(os.path.normpath(os.path.dirname(inspect.getfile(cls))))
    resourcesPath = os.path.join(modulePath, 'Resources/Icons')
    dictionary = dict()
    for filename in os.listdir(resourcesPath):
      if not filename.startswith("icon-") or not filename.endswith(".png"):
        continue
      name = filename.replace("icon-", "").replace(".png", "").replace("-", "_").replace(" ", "_")
      name = re.sub('(?<!^)(?=[A-Z])', '_', name).lower().replace("__", "_")
      dictionary[name] = filename
    return dictionary

  _ICONS = _getDictionaryFromDirectory

  @classmethod
  def getIcon(cls, name):
    """ Returning a QIcon for the retrieved icon name. Throws an exception if the name was not found.
    """
    if not name in cls._ICONS.keys():
      raise ValueError("Attribute %s is not defined." % name)
    return qt.QIcon(cls.getPath(name))

  @classmethod
  def getPath(cls, name):
    """ Returns the path to a specific icon. """
    modulePath = os.path.dirname(os.path.normpath(os.path.dirname(inspect.getfile(cls))))
    return os.path.join(modulePath, 'Resources/Icons', cls._ICONS[name])

  def __getattr__(cls, attr):
    if not attr in cls._ICONS.keys():
      raise AttributeError("Attribute %s is not defined." % attr)
    icon = cls.getIcon(attr)
    setattr(cls, attr, icon)
    return getattr(cls, attr)


class Icons(object):
  """ The Icons class provides a bunch of frequently used icons.

  All icons from ``names`` can directly be accessed by using ``Icons.{name from names list}`` (i.e. ``Icons.apply``)


  .. code-block:: python

    from SlicerDevelopmentToolboxUtils.icons import Icons
    Icons.names

    # a icon can be retrieved by calling Icons.{name}

    applyIcon = Icons.apply
    sideBySideIcon = Icons.layout_side_by_side_view
  """

  __metaclass__ = IconsMetaClass

  @classproperty
  def names(cls):
    return sorted(cls._ICONS.keys())

  @classmethod
  def getPath(cls, name):
    return IconsMetaClass.getPath(cls, name)