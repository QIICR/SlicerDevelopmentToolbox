cmake_minimum_required(VERSION 3.13.4)

project(SlicerDevelopmentToolbox)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "http://wiki.slicer.org/slicerWiki/index.php/Documentation/Nightly/Extensions/SlicerDevelopmentToolbox")
set(EXTENSION_CATEGORY "Informatics Utilities 'Developer Tools'")
set(EXTENSION_CONTRIBUTORS "Christian Herz (Brigham and Women's Hospital), Andrey Fedorov (Brigham and Women's Hospital)")
set(EXTENSION_DESCRIPTION "SlicerDevelopmentToolbox extension facilitates the development process of modules/extensions with a large variety of widgets, helpers, decorators, events, constants and mixin classes")
set(EXTENSION_ICONURL "http://raw.githubusercontent.com/QIICR/SlicerDevelopmentToolbox/master/Resources/Icons/SlicerDevelopmentToolbox.png")
set(EXTENSION_SCREENSHOTURLS "")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
set(MODULE_NAME SlicerDevelopmentToolbox)

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  ${MODULE_NAME}Utils/__init__.py
  ${MODULE_NAME}Utils/mixins.py
  ${MODULE_NAME}Utils/helpers.py
  ${MODULE_NAME}Utils/constants.py
  ${MODULE_NAME}Utils/decorators.py
  ${MODULE_NAME}Utils/metaclasses.py
  ${MODULE_NAME}Utils/events.py
  ${MODULE_NAME}Utils/exceptions.py
  ${MODULE_NAME}Utils/widgets.py
  ${MODULE_NAME}Utils/icons.py
  ${MODULE_NAME}Utils/buttons.py
  ${MODULE_NAME}Utils/module/__init__.py
  ${MODULE_NAME}Utils/module/base.py
  ${MODULE_NAME}Utils/module/session.py
  ${MODULE_NAME}Utils/module/logic.py
  ${MODULE_NAME}Utils/module/plugin.py
  ${MODULE_NAME}Utils/module/step.py
  ${MODULE_NAME}Utils/forms/__init__.py
  ${MODULE_NAME}Utils/forms/FormGenerator.py
  ${MODULE_NAME}Utils/forms/FormGeneratorFactory.py
  ${MODULE_NAME}Utils/forms/JSONFormGenerator.py
  ${MODULE_NAME}Utils/forms/FormsDialog.py
  )

file(GLOB_RECURSE MODULE_PYTHON_RESOURCES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR}
  ${PROJECT_SOURCE_DIR}/Resources/Icons/*
  ${PROJECT_SOURCE_DIR}/Resources/UI/*
)

#-----------------------------------------------------------------------------
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  )

if(BUILD_TESTING)
  add_subdirectory(Testing)
endif()

#-----------------------------------------------------------------------------

include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})