import vtk
import ctk
import json
from collections import OrderedDict

from .FormGenerator import *

from SlicerDevelopmentToolboxUtils.mixins import UICreationHelpers, GeneralModuleMixin

# TODO: definitions are not resolved right now


class JSONFormGenerator(FormGenerator):

  CustomFrameClass = GeneratedFrame

  def generate(self, defaultSettings=None):
    with open(self.filePath) as data_file:
      data = json.load(data_file, object_pairs_hook=OrderedDict)
      return self._generate(data, defaultSettings)

  def _generate(self, schema, defaultSettings=None):
    return JSONObjectField("", schema, defaultSettings)


class JSONFieldFactory(object):

  @staticmethod
  def getJSONFieldClass(schema):
    dataType = schema.get('type')
    if dataType == "object":
      return JSONObjectField
    elif schema.has_key("enum"):
        return JSONEnumField
    else:
      if dataType == "string":
        return JSONStringField
      elif dataType == "integer":
        return JSONIntegerField
      elif dataType == "number":
        return JSONNumberField
      # elif dataType == "array":
      #   return JSONArrayField
    raise ValueError("Schema %s cannot be handled by %s" % (schema, JSONFieldFactory.__name__))


class AbstractField(GeneralModuleMixin):

  UpdateEvent = vtk.vtkCommand.UserEvent + 100
  ResizeEvent = vtk.vtkCommand.UserEvent + 101

  def __init__(self, schema, defaultSettings=None):
    self._defaultSettings = defaultSettings
    self._type = schema.get('type')
    self._schema = schema
    self.setup()

  def setup(self):
    return NotImplementedError

  def getData(self):
    return NotImplementedError

  def setData(self, data):
    # TODO: needs to iterate trough objects etc.
    # editable?
    raise NotImplementedError

  def execAndGetReturnValue(self, code):
    code = code.replace("callback:", "")
    commands = filter((lambda x: len(x) > 0), code.split(';'))
    for idx, command in enumerate(commands):
      if idx == len(commands)-1:
        break
      exec command in locals()
    exec "returnValue={}".format(commands[-1]) in locals()
    return returnValue


class AbstractFieldWidget(qt.QWidget, AbstractField):

  def __init__(self, title, schema, defaultSettings=None, parent=None):
    self._elem = None
    self._data = dict()
    self.title = title
    qt.QWidget.__init__(self, parent)
    AbstractField.__init__(self, schema, defaultSettings)

  def getDefaultValue(self):
    value = None
    if self._defaultSettings:
      value = self._defaultSettings.value(self.title)
    if not value and self._schema.get("default"):
      value = self._schema["default"]
      value = self.execAndGetReturnValue(value) if type(value) in [str, unicode] and "callback:" in value else value
    return value

  def getData(self):
    return self._data

  def getElement(self):
    return self._elem

  def _updateData(self, key, value):
    try:
      value = JSONTypeConverter.getPythonType(self._type)(value)
    except ValueError:
      value = None

    if not value:
      self._data.pop(key, None)
    else:
      self._data[key] = value
    self.invokeEvent(self.UpdateEvent, str([key, value]))


class JSONObjectField(qt.QWidget, AbstractField):

  @property
  def title(self):
    if self._subWidget:
      return getattr(self._subWidget, "title" if isinstance(self._subWidget, qt.QGroupBox) else "text")
    return self._title

  @title.setter
  def title(self, value):
    if not self._subWidget:
      self._title = value
    else:
      setattr(self._subWidget, "title" if isinstance(self._subWidget, qt.QGroupBox) else "text", value)

  def __init__(self, title, schema, defaultSettings=None, parent=None):
    self.elements = []
    self._subWidget = None
    self.title = title
    qt.QWidget.__init__(self, parent)
    AbstractField.__init__(self, schema, defaultSettings)

  def setup(self):
    self.setLayout(qt.QVBoxLayout())
    # keywords to handle: required, properties
    # description?
    # title?
    schema = self._schema
    self._setupSubWidget()
    if self._schema.get("description"):
      self.setToolTip(self._schema["description"])
    if self._schema.get('properties'):
      schema = self._schema['properties']
    for title, obj in schema.items():
      fieldObjectClass = JSONFieldFactory.getJSONFieldClass(obj)
      self._addElement(fieldObjectClass(title, obj, self._defaultSettings))
    self.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)

  def _setupSubWidget(self):
    if self._schema.get("collapsible") is True:
      self._subWidget = ctk.ctkCollapsibleButton()
      if self._schema.get("collapsed"):
        self._subWidget.collapsed = self._schema.get("collapsed")
      self._subWidget.contentsCollapsed.connect(self.onCollapsed)
    else:
      self._subWidget = qt.QGroupBox(self._title)

    self.title = self._schema.get("title") if self._schema.get("title") else self._title

    self._subWidget.setLayout(qt.QFormLayout())
    self.layout().addWidget(self._subWidget)

  def onCollapsed(self, collapsed):
    qt.QTimer.singleShot(50, lambda: self.invokeEvent(self.ResizeEvent))

  def _addElement(self, elem):
    if isinstance(elem, JSONObjectField):
      self._subWidget.layout().addWidget(elem)
      elem.addEventObserver(self.ResizeEvent, lambda caller, event: self.invokeEvent(self.ResizeEvent))
    else:
      self._subWidget.layout().addRow(elem.title, elem)
    self.elements.append(elem)

  def getData(self):
    data = dict()
    for elem in self.elements:
      data.update(elem.getData())
    return data if not self.title else {self.title: data}


class JSONArrayField(qt.QGroupBox, AbstractField):
  # TODO implement
  pass


class JSONEnumField(AbstractFieldWidget):

  def setup(self):
    self.setLayout(qt.QFormLayout())
    widgetClass = self._schema.get("ui:widget", "combo")
    if widgetClass == "radio":
      self._elem = self.__setupRadioButtonGroup()
    else:
      self._elem = self.__setupComboBox()
    if self._schema.get("description"):
      self._elem.setToolTip(self._schema["description"])
    self.layout().addWidget(self._elem)

  def __setupComboBox(self):
    elem = qt.QComboBox()
    elem.connect("currentIndexChanged(QString)",
                 lambda text: self._updateData(self.title, text))
    self.destroyed.connect(lambda: elem.disconnect("currentIndexChanged(QString)"))
    elem.addItems(self._schema["enum"])
    return elem

  def __setupRadioButtonGroup(self):
    elem = qt.QFrame()
    elem.setLayout(qt.QVBoxLayout())
    self.__buttonGroup = qt.QButtonGroup()
    self.__buttonGroup.setExclusive(True)
    self.__buttonGroup.connect("buttonClicked(QAbstractButton*)",
                               lambda button: self._updateData(self.title, button.text))
    self.destroyed.connect(lambda: self.__buttonGroup.disconnect("buttonClicked(QAbstractButton*)"))
    for e in self._schema["enum"]:
      b = UICreationHelpers.createRadioButton(e, name=e)
      elem.layout().addWidget(b)
      self.__buttonGroup.addButton(b)
    return elem


class JSONStringField(AbstractFieldWidget):

  def setup(self):
    self.setLayout(qt.QFormLayout())
    widgetClass = self._schema.get("ui:widget", "line")
    if widgetClass == "textarea":
      self._elem = self._setupTextArea()
    else:
      self._elem = self._setupLineEdit()
    self._configureAdditionalElementAttributes()
    self.layout().addWidget(self._elem)

  def _configureAdditionalElementAttributes(self):
    if self._schema.get("maxLength"):
      self._elem.setMaxLength(self._schema["maxLength"])
    default = self.getDefaultValue()
    if default:
      self._elem.setText(default)
    if self._schema.get("description"):
      self._elem.setToolTip(self._schema["description"])
    self.destroyed.connect(lambda: self._elem.textChanged.disconnect())

  def _setupTextArea(self):
    elem = qt.QTextEdit()
    elem.textChanged.connect(lambda: self._updateData(self.title, elem.toPlainText()))
    return elem

  def _setupLineEdit(self):
    # has pattern?
    elem = qt.QLineEdit()
    elem.textChanged.connect(lambda text: self._updateData(self.title, text))
    return elem


class JSONNumberField(AbstractFieldWidget):

  validatorClass = qt.QDoubleValidator

  def setup(self):
    self.setLayout(qt.QFormLayout())
    self._configureValidator()
    self._elem = qt.QLineEdit()
    self._connectField()
    self._elem.setValidator(self._validator)
    default = self.getDefaultValue()
    if default:
      self._elem.setText(default)
    if self._schema.get("description"):
      self._elem.setToolTip(self._schema["description"])
    self.layout().addWidget(self._elem)

  def _connectField(self):
    self._elem.textChanged.connect(lambda n: self._updateData(self.title, n))
    self.destroyed.connect(lambda: self._elem.textChanged.disconnect())

  def _configureValidator(self):
    self._validator = self.validatorClass()
    if self._schema.get("minimum"):
      self._validator.setBottom(self._schema.get("minimum"))
    if self._schema.get("maximum"):
      self._validator.setTop(self._schema.get("maximum"))
    return self._validator


class JSONIntegerField(JSONNumberField):

  validatorClass = qt.QIntValidator

  def _connectField(self):
    self._elem.textChanged.connect(lambda n: self._updateData(self.title, n))
    self.destroyed.connect(lambda: self._elem.textChanged.disconnect())


class JSONTypeConverter(object):

  @staticmethod
  def getPythonType(jsonType):
    if jsonType == 'number':
      return float
    elif jsonType == 'integer':
      return int
    elif jsonType == 'string':
      return str
    elif jsonType == 'boolean':
      return bool
    return None