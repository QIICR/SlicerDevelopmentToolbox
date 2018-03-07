import os
from .JSONFormGenerator import JSONFormGenerator


class FormGeneratorFactory(object):

  @staticmethod
  def getFormGenerator(filePath):

    fileName, fileExtension = os.path.splitext(filePath)

    if fileExtension.lower() == '.json':
      return JSONFormGenerator(filePath)
    else:
      raise ValueError("File extension %s is not supported right now" % fileExtension)