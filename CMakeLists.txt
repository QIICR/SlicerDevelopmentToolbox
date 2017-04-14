cmake_minimum_required(VERSION 2.8.9)

project(SlicerDevelopmentToolbox)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "http://wiki.slicer.org/slicerWiki/index.php/Documentation/Nightly/Extensions/SlicerDevelopmentToolbox")
set(EXTENSION_CATEGORY "Informatics Utilities 'Developer Tools'")
set(EXTENSION_CONTRIBUTORS "Christian Herz (Brigham and Women's Hospital), Andrey Fedorov (Brigham and Women's Hospital)")
set(EXTENSION_DESCRIPTION "SlicerDevelopmentToolbox extension facilitates the development process of modules/extensions with a large variety of widgets, helpers, decorators, events, constants and mixin classes")
set(EXTENSION_ICONURL "http://wiki.slicer.org/slicerWiki/images/8/87/SlicerDevelopmentToolbox_Logo_1.0_128x128.png")
set(EXTENSION_SCREENSHOTURLS "")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
if(NOT Slicer_SOURCE_DIR)
  include(${Slicer_EXTENSION_CPACK})
endif()

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
  ${MODULE_NAME}Utils/signal.py
  ${MODULE_NAME}Utils/events.py
  ${MODULE_NAME}Utils/widgets.py
  ${MODULE_NAME}Utils/buttons.py
  )

set(MODULE_PYTHON_RESOURCES
  Resources/Icons/icon-addFiducial.png
  Resources/Icons/icon-modifyFiducial.png
  Resources/Icons/icon-apply.png
  Resources/Icons/cursor-window-level.png
  Resources/Icons/icon-settings.png
  Resources/Icons/icon-star-filled.png
  Resources/Icons/icon-star-unfilled.png
  Resources/Icons/LayoutFourUpView.png
  Resources/Icons/LayoutFourUpTableView.png
  Resources/Icons/LayoutOneUpRedSliceView.png
  Resources/Icons/LayoutSideBySideView.png
  Resources/Icons/SlicesCrosshair.png
  Resources/Icons/icon-WindowLevelEffect.png
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