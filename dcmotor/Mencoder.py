import time, logging
import pigpio # http://abyz.co.uk/rpi/pigpio/python.html

class Encoder:
   """
   A class to read speedometer pulses and calculate the RPM.
   """
   def __init__(self, pi, gpio, rpmkey='rpmi', pulses_per_rev=20.0, weighting=0.0, min_RPM=5.0, logger=None):
      """
      Instantiate with the Pi and gpio of the RPM signal
      to monitor.
      Optionally the number of pulses for a complete revolution
      may be specified.  It defaults to 1.
      Optionally a weighting may be specified.  This is a number
      between 0 and 1 and indicates how much the old reading
      affects the new reading.  It defaults to 0 which means
      the old reading has no effect.  This may be used to
      smooth the data.
      Optionally the minimum RPM may be specified.  This is a
      number between 1 and 1000.  It defaults to 5.  An RPM
      less than the minimum RPM returns 0.0.
      """
      self.pi = pi
      self.gpio = gpio
      self.rpmkey = rpmkey
      self.outgoing = {}
      self.pulses_per_rev = pulses_per_rev
      if logger is not None:                        # Use logger passed as argument
            self.logger = logger
      elif len(logging.getLogger().handlers) == 0:   # Root logger does not exist and no custom logger passed
         logging.basicConfig(level=logging.DEBUG)      # Create root logger
         self.logger = logging.getLogger(__name__)    # Create from root logger
      else:                                          # Root logger already exists and no custom logger passed
         self.logger = logging.getLogger(__name__)    # Create from root logger     

      if min_RPM > 1000.0:
         min_RPM = 1000.0
      elif min_RPM < 1.0:
         min_RPM = 1.0

      self.min_RPM = min_RPM

      self._watchdog = 200 # Milliseconds.

      if weighting < 0.0:
         weighting = 0.0
      elif weighting > 0.99:
         weighting = 0.99

      self._new = 1.0 - weighting # Weighting for new reading.
      self._old = weighting       # Weighting for old reading.

      self._high_tick = None
      self._period = None

      pi.set_mode(gpio, pigpio.INPUT)

      self._cb = pi.callback(gpio, pigpio.RISING_EDGE, self._cbf)
      pi.set_watchdog(gpio, self._watchdog)
      self.logger.info(self._cb)

   def _cbf(self, gpio, level, tick):   # gpio is pin with level change. level is rising/falling(or none), tick is time counter (usec)

      if level == 1: # Rising edge.
         if self._high_tick is not None:
            t = pigpio.tickDiff(self._high_tick, tick)
            if self._period is not None:
               self._period = (self._old * self._period) + (self._new * t)
            else:
               self._period = t
         if self._period is not None: self.logger.debug("period:{0:.1f} ms".format(self._period/1000))
         self._high_tick = tick
      elif level == 2: # Watchdog timeout.
         if self._period is not None:
            if self._period < 2000000000:
               self._period += (self._watchdog * 1000)

   def getdata(self):
      """
      Returns the RPM.
      """
      RPM = 0.0
      if self._period is not None:
         RPM = 60000000.0 / (self._period * self.pulses_per_rev)  # min(us)/(period(us)*pulse/rev)
         if RPM < self.min_RPM:
            RPM = 0.0
      self.outgoing[self.rpmkey] = int(RPM)
      return self.outgoing

   def cancel(self):
      """
      Cancels the Encoder and releases resources.
      """
      self.pi.set_watchdog(self.gpio, 0) # cancel watchdog
      self._cb.cancel()

if __name__ == "__main__":

   import time
   import pigpio

   gpioPin = 5
   RUN_TIME = 60.0
   SAMPLE_TIME = 1.0
   pi = pigpio.pi()
   encoder1 = Encoder(pi, gpioPin)
   start = time.time()
   while (time.time() - start) < RUN_TIME:
      time.sleep(SAMPLE_TIME)
      rpm = encoder1.getdata()
      print(rpm)
   encoder1.cancel()
   pi.stop()