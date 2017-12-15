from functools import wraps
import itertools
import logging
import inspect
import slicer


class logmethod(object):
  """ This decorator can be used for logging methods without the need of reimplementing log messages over and over again.

  The decorator logs information about the called method name including caller and arguments.

  .. code-block:: python

    from SlicerDevelopmentToolboxUtils.decorators import logmethod

    @logmethod()
    def sub(x,y, switch=False):
      return x -y if not switch else y-x

    @logmethod(level=logging.INFO)
    def sub(x,y, switch=False):
      return x -y if not switch else y-x
  """

  def __init__(self, level=logging.DEBUG):
    self.logLevel = level

  def __call__(self, func):
    def wrapped_f(*args, **kwargs):
      args_map = {}
      try:
        if args or kwargs:
          args_map = inspect.getcallargs(func, *args, **kwargs)
      except TypeError:
        pass
      className = ""
      if 'self' in args_map:
        cls = args_map['self'].__class__
        className = cls.__name__ + '.'
      try:
        frame = inspect.stack()[1][0]
        fileName = frame.f_code.co_filename
        lineNo = frame.f_lineno
        callerMethod = frame.f_code.co_name
        callerClass = frame.f_locals["self"].__class__.__name__
      except (KeyError, IndexError):
        callerClass = callerMethod = lineNo = fileName = ""
      caller = ""
      if callerClass != "" and callerMethod != "":
        caller = " from {}.{}".format(callerClass, callerMethod)
      logging.log(self.logLevel, "Called {}{}{} with args {} and "
                                 "kwargs {} from file {} line {} ".format(className, func.__name__, caller, args,
                                                                          kwargs, fileName, lineNo))
      return func(*args, **kwargs)
    return wrapped_f


class onModuleSelected(object):
  """ This decorator can be used for executing the decorated function/method only if a certain Slicer module with name
      moduleName is currently selected

  .. code-block:: python

    from SlicerDevelopmentToolboxUtils.decorators import onModuleSelected

    @onModuleSelected(moduleName="SliceTracker")
    def onLayoutChanged(self, layout=None):
      print "layout changed"
  """

  def __init__(self, moduleName):
    self.moduleName = moduleName

  def __call__(self, func):
    def wrapped_f(*args, **kwargs):
      currentModuleName = slicer.util.selectedModule()
      if currentModuleName == self.moduleName:
        return func(*args, **kwargs)
      else:
        logging.debug("Method {} not executed: \n  Selected module: {}\n  Expected module: {}"
                      .format(func, currentModuleName, self.moduleName))
    return wrapped_f


def onExceptionReturnNone(func):
  """ Whenever an exception occurs within the decorated function, this decorator will return None

  .. code-block:: python

    from SlicerDevelopmentToolboxUtils.decorators import onExceptionReturnNone
    @onExceptionReturnNone
    def getElement(key, dictionary):
      return dictionary[key]

    result = getElement('foobar', {'foo':1, 'bar':2}) # no foobar in dictionary
  """

  @wraps(func)
  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except (IndexError, AttributeError, KeyError):
      return None
  return wrapper


def onExceptionReturnFalse(func):
  """ Whenever an exception occurs within the decorated function, this decorator will return False

  .. doctest::

      >>> from SlicerDevelopmentToolboxUtils.decorators import onExceptionReturnFalse
      >>> @onExceptionReturnFalse
      ... def getElement(key, dictionary):
      ...   return dictionary[key]

      >>> result = getElement('foobar', {'foo':1, 'bar':2}) # no foobar in dictionary
      >>> result is False
  """

  @wraps(func)
  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except:
      return False
  return wrapper


def onReturnProcessEvents(func):
  """ After running the decorated function slicer.app.processEvents() will be executed
  """

  @wraps(func)
  def wrapper(*args, **kwargs):
    func(*args, **kwargs)
    slicer.app.processEvents()
  return wrapper


def beforeRunProcessEvents(func):
  """ Before running the decorated function slicer.app.processEvents() will be executed
  """

  @wraps(func)
  def wrapper(*args, **kwargs):
    slicer.app.processEvents()
    func(*args, **kwargs)
  return wrapper


def callCount(level=logging.DEBUG):
  """ This decorator is useful for debugging purposes where one wants to know the call count of the decorated function.
  """

  def decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
      args_map = {}
      if args or kwargs:
        args_map = inspect.getcallargs(func, *args, **kwargs)
      className = ""
      if 'self' in args_map:
        cls = args_map['self'].__class__
        className = cls.__name__ + '.'
      wrapper.count += 1
      logging.log(level, "{}{} called {} times".format(className, func.__name__, wrapper.count))
      return func(*args, **kwargs)

    wrapper.count = 0
    return wrapper
  return decorator


class MultiMethodRegistrations:

  registry = {}

class MultiMethod:
  """ Helper class for keeping track of multimethod decorated methods

  See Also: http://www.artima.com/weblogs/viewpost.jsp?thread=101605
  """
  def __init__(self, name):
    self.__name__ = name
    self.name = name
    self.typemap = {}

  def __call__(self, *args, **kwargs):
    types = tuple(arg.__class__ for arg in args) # a generator expression!
    function = self.typemap.get(types)
    if function is None:
      raise TypeError("no match for types %s" % str(types))
    return function(*args)
  def register(self, types, function):
    if types in self.typemap:
      raise TypeError("duplicate registration")
    self.typemap[types] = function


def multimethod(*types):
  """ This decorator can be used to define different signatures of a method/function for different data types

  .. doctest::

      @multimethod([int, float], [int, float], str)
      def foo(arg1, arg2, arg3):
        print arg1, arg2, arg3

      @multimethod([int, float], str)
      def foo(arg1, arg2, arg3):
        print arg1, arg2, arg3

      foo(1,2,"bar")
      foo(1.0,2,"bar")
      foo(1,2.0,"bar")
      foo(1.0,2.0,"bar")

  See Also: http://www.artima.com/weblogs/viewpost.jsp?thread=101605
  """

  def register(func):
    name = func.__name__
    mm = MultiMethodRegistrations.registry.get(name)
    if mm is None:
      mm = MultiMethodRegistrations.registry[name] = MultiMethod(name)
    for combination in list(itertools.product(*[[t] if type(t) is not list else t for t in types], repeat=1)):
      mm.register(combination, func)
    return mm
  return register


def timer(func):
  """ This decorator can be used for profiling a method/function by printing the elapsed time after execution.
  """
  def _new_function(*args, **kwargs):
    import time
    startTime = time.time()
    x = func(*args, **kwargs)
    duration = time.time() - startTime
    print "{} ran in: {0} seconds".format(func.__name__, duration)
    return x

  return _new_function


class processEventsEvery:
  """ Decorator for executing a method/function every n milli seconds.
  """

  def __init__(self, interval=100):
    import qt
    self.timer = qt.QTimer()
    self.timer.setInterval(interval)
    self.timer.connect('timeout()', self.onTriggered)

  def __del__(self):
    self.timer.disconnect('timeout()')

  def __call__(self, func):
    def wrapped_f(*args, **kwargs):
      self.timer.start()
      func(*args, **kwargs)
      self.timer.stop()
    return wrapped_f

  def onTriggered(self):
    slicer.app.processEvents()


def priorCall(functionToCall):
  """ This decorator calls functionToCall prior to the decorated function.

  Args:
    functionToCall(function): function to be called prior(before) the decorated function
  """
  def decorator(func):
    @wraps(func)
    def f(*args, **kwargs):
      logging.debug("calling {} before {}".format(functionToCall.__name__, func.__name__))
      functionToCall(args[0])
      func(*args, **kwargs)
    return f
  return decorator


def postCall(functionToCall):
  """ This decorator calls functionToCall after the decorated function.

  Args:
    functionToCall(function): function to be called after the decorated function
  """
  def decorator(func):
    @wraps(func)
    def f(*args, **kwargs):
      logging.debug("calling {} after {}".format(functionToCall.__name__, func.__name__))
      func(*args, **kwargs)
      functionToCall(args[0])
    return f
  return decorator


def singleton(cls):
  """ This decorator makes sure that only one instance of the decorated class will be created (singleton).

  See Also: http://stackoverflow.com/questions/12305142/issue-with-singleton-python-call-two-times-init
  """
  instances = {}

  def getinstance(*args, **kwargs):
    if cls not in instances:
      instances[cls] = cls(*args, **kwargs)
    return instances[cls]

  return getinstance


class classproperty(object):
  """ This decorator enables adding properties to classes that can be called without instantiating an object

  See Also: https://stackoverflow.com/a/13624858
  """

  def __init__(self, fget):
    self.fget = fget

  def __get__(self, owner_self, owner_cls):
    return self.fget(owner_cls)