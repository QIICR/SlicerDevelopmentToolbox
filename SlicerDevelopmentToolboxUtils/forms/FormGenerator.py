from __future__ import absolute_import
from abc import abstractmethod, ABCMeta
import qt

class FormGenerator(metaclass=ABCMeta):

  CustomFrameClass = None

  def __init__(self, filePath):
    self.filePath = filePath
    if not self.CustomFrameClass:
      raise NotImplementedError("All concrete classes need to implement member CustomFrameClass")

  @abstractmethod
  def generate(self):
    pass

  @abstractmethod
  def _generate(self, data):
    pass

  def _createLabel(self, title, **kwargs):
    label = qt.QLabel(title)
    return self._extendQtGuiElementProperties(label, **kwargs)

  def _createLineEdit(self, title, **kwargs):
    lineEdit = qt.QLineEdit(title)
    return self._extendQtGuiElementProperties(lineEdit, **kwargs)

  def _createTextEdit(self, title, **kwargs):
    textEdit = qt.QTextEdit(title)
    return self._extendQtGuiElementProperties(textEdit, **kwargs)

  def _createComboBox(self, **kwargs):
    comboBox = qt.QComboBox()
    return self._extendQtGuiElementProperties(comboBox, **kwargs)

  def _extendQtGuiElementProperties(self, element, **kwargs):
    for key, value in kwargs.items():
      if hasattr(element, key):
        setattr(element, key, value)
      else:
        import logging
        logging.error("%s does not have attribute %s" % (element.className(), key))
    return element

  @classmethod
  def _initializeCustomForm(cls):
    form = cls.CustomFrameClass()
    form.setLayout(qt.QFormLayout())
    return form


class GeneratedFrame(qt.QFrame):
  # TODO: it might make sense to use a design pattern here as well since users/developers
  #       might want to get the data in a different format

  def __init__(self):
    qt.QFrame.__init__(self)

  def getData(self):
    # TODO: iterate through ui elements and return as preferred format
    pass
