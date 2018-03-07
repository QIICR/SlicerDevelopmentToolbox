import vtk
import json
from collections import OrderedDict

from .FormGenerator import *

from SlicerDevelopmentToolboxUtils.mixins import UICreationHelpers, ParameterNodeObservationMixin


# TODO: definitions are not resolved right now


class JSONFormGenerator(FormGenerator):

  CustomFrameClass = GeneratedFrame

  def generate(self):
    with open(self.filePath) as data_file:
      data = json.load(data_file, object_pairs_hook=OrderedDict)
      return self._generate(data)

  def _generate(self, schema):
    return JSONObjectField("", schema)


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


class AbstractField(ParameterNodeObservationMixin):

  UpdateEvent = vtk.vtkCommand.UserEvent + 100

  def __init__(self, title, schema):
    self._type = schema.get('type')
    self.title = title
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


class AbstractFieldWidget(qt.QWidget, AbstractField):

  def __init__(self, title, schema, parent=None):
    self._elem = None
    self._data = dict()
    qt.QWidget.__init__(self, parent)
    AbstractField.__init__(self, title, schema)

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


class JSONObjectField(qt.QGroupBox, AbstractField):

  def __init__(self, title, schema, parent=None):
    self.elements = []
    qt.QGroupBox.__init__(self, parent)
    AbstractField.__init__(self, title, schema)

  def setup(self):
    self.setLayout(qt.QFormLayout())
    # keywords to handle: required, properties
    # description?
    # title?
    schema = self._schema
    if self._schema.get("title"):
      self.title = self._schema.get("title")
    if self._schema.get("description"):
      self.setToolTip(self._schema["description"])
    if self._schema.get('properties'):
      schema = self._schema['properties']
    for title, elem in schema.items():
      fieldObjectClass = JSONFieldFactory.getJSONFieldClass(elem)
      self._addElement(fieldObjectClass(title, elem))

  def _addElement(self, elem):
    if isinstance(elem, JSONObjectField):
      self.layout().addWidget(elem)
    else:
      self.layout().addRow(elem.title, elem)
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
    elem.addItems(self._schema["enum"])
    return elem

  def __setupRadioButtonGroup(self):
    elem = qt.QFrame()
    elem.setLayout(qt.QVBoxLayout())
    self.__buttonGroup = qt.QButtonGroup()
    self.__buttonGroup.setExclusive(True)
    self.__buttonGroup.connect("buttonClicked(QAbstractButton*)",
                               lambda button: self._updateData(self.title, button.text))
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
    if self._schema.get("default"):
      default = self._schema["default"]
      self._elem.setText(default)
    if self._schema.get("description"):
      self._elem.setToolTip(self._schema["description"])

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
    if self._schema.get("default"):
      self._elem.setText(self._schema["default"])
    if self._schema.get("description"):
      self._elem.setToolTip(self._schema["description"])
    self.layout().addWidget(self._elem)

  def _connectField(self):
    self._elem.textChanged.connect(lambda n: self._updateData(self.title, n))

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