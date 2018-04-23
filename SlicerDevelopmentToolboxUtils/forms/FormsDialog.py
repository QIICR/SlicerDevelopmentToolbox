import qt
import os
import slicer

from .FormGeneratorFactory import FormGeneratorFactory


class FormsDialog(qt.QDialog):

  @property
  def currentForm(self):
    return self._currentForm

  @currentForm.setter
  def currentForm(self, form):
    if self._currentForm is not None:
      self._currentForm.form.setParent(None)
      self._uiLayout.removeWidget(self._currentForm.form)
    self._currentForm = form
    if self._currentForm:
      self._uiLayout.addWidget(form.form, 1, 1)
    self.updateNavigationButtons()
    self.onResize()

  def __init__(self, schemaFiles, defaultSettings=None, parent=None):
    qt.QDialog.__init__(self, parent)
    self._defaultSettings = defaultSettings
    self.logic = FormsDialogLogic(schemaFiles)

    self.formWidgets = list()
    self.setup()
    self._setupConnections()

  def setup(self):
    self.setLayout(qt.QGridLayout())
    self._loadUI()

    self.generateFormWidgets()
    self.currentForm = self.formWidgets[0]

    self.updateNavigationButtons()

    self.layout().addWidget(self.ui)

  def onResize(self, caller=None, event=None):
    slicer.app.processEvents()
    self.adjustSize()

  def _loadUI(self):
    import inspect
    modulePath = os.path.dirname(os.path.normpath(os.path.dirname(inspect.getfile(self.__class__))))
    modulePath = modulePath.replace("SlicerDevelopmentToolboxUtils", "")
    path = os.path.join(modulePath, 'Resources', 'UI', 'FormsDialog.ui')
    self.ui = slicer.util.loadUI(path)
    self._uiLayout = self.ui.findChild(qt.QGridLayout, "gridLayout")
    self._prevButton = self.ui.findChild(qt.QPushButton, "prevButton")
    self._nextButton = self.ui.findChild(qt.QPushButton, "nextButton")
    self._buttonBox = self.ui.findChild(qt.QDialogButtonBox, "buttonBox")
    self._navigationBar = self.ui.findChild(qt.QWidget, "navigationBar")

  def _setupConnections(self):
    def setupConnections(funcName="connect"):
      getattr(self._buttonBox.accepted, funcName)(self._onAccept)
      getattr(self._buttonBox.rejected, funcName)(self._onReject)
      getattr(self._prevButton.clicked, funcName)(self._onPrevButtonClicked)
      getattr(self._nextButton.clicked, funcName)(self._onNextButtonClicked)

    setupConnections()
    slicer.app.connect('aboutToQuit()', self.deleteLater)
    self.destroyed.connect(lambda : setupConnections(funcName="disconnect"))

  def updateNavigationButtons(self):
    self._prevButton.setEnabled(self._currentForm is not None and self._currentForm.hasPrev())
    self._nextButton.setEnabled(self._currentForm is not None and self._currentForm.hasNext())

  def _onPrevButtonClicked(self):
    self.currentForm = self._currentForm.prevForm

  def _onNextButtonClicked(self):
    self.currentForm = self._currentForm.nextForm

  def _onAccept(self):
    # persist data for forms
    self.accept()

  def _onReject(self):
    self.reject()

  def generateFormWidgets(self):
    self._currentForm = None
    for form in self.logic.schemaFiles:
      gen = FormGeneratorFactory.getFormGenerator(form)
      newForm = DoublyLinkedForms(gen.generate(self._defaultSettings))
      newForm.form.addEventObserver(newForm.form.ResizeEvent, self.onResize)
      self.formWidgets.append(newForm)
      if self._currentForm:
        newForm.prevForm = self._currentForm
        self._currentForm.nextForm = newForm
      self._currentForm = newForm
    self._navigationBar.visible = len(self.logic.schemaFiles) > 1

  def getData(self):
    data = dict()
    for form in self.formWidgets:
      data.update(form.form.getData())
    return data


class FormsDialogLogic(object):

  @property
  def schemaFiles(self):
    return self._schemaFiles

  @schemaFiles.setter
  def schemaFiles(self, schemaFiles):
    if type(schemaFiles) is str:
      schemaFiles = [schemaFiles]
    elif type(schemaFiles) is list:
      pass
    else:
      raise ValueError("Value %s is not valid for schema files. It has to be either a list or a string" % schemaFiles)
    self._schemaFiles = schemaFiles

  def __init__(self, schemaFiles):
    self.schemaFiles = schemaFiles


class DoublyLinkedForms(object):

  def __init__(self, form):
    self.form = form
    self.nextForm = None
    self.prevForm = None

  def hasNext(self):
    return self.nextForm is not None

  def hasPrev(self):
    return self.prevForm is not None