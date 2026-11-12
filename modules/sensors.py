"""HC-SR04 Dual Ultrasonic Distance Sensors — Front + Back."""
import time

try:
    import RPi.GPIO as GPIO
    _HW = True
except ImportError:
    _HW = False
    print("[SENSOR] RPi.GPIO not found — running in simulation mode")

import config


class UltrasonicSensor:
    def __init__(self):
        if _HW:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            # Front sensor
            GPIO.setup(config.ULTRA_TRIG, GPIO.OUT)
            GPIO.setup(config.ULTRA_ECHO, GPIO.IN)
            GPIO.output(config.ULTRA_TRIG, False)
            # Back sensor
            GPIO.setup(config.ULTRA_TRIG2, GPIO.OUT)
            GPIO.setup(config.ULTRA_ECHO2, GPIO.IN)
            GPIO.output(config.ULTRA_TRIG2, False)
            time.sleep(0.05)
        print("[SENSOR] Dual ultrasonic ready (front + back)")

    def get_distance(self):
        """Return FRONT distance in cm."""
        return self._read(config.ULTRA_TRIG, config.ULTRA_ECHO)

    def get_front_distance(self):
        """Return front sensor distance in cm."""
        return self._read(config.ULTRA_TRIG, config.ULTRA_ECHO)

    def get_back_distance(self):
        """Return back sensor distance in cm."""
        return self._read(config.ULTRA_TRIG2, config.ULTRA_ECHO2)

    def _read(self, trig, echo):
        """Read distance from a specific sensor."""
        if not _HW:
            return 999

        GPIO.output(trig, True)
        time.sleep(0.00001)
        GPIO.output(trig, False)

        deadline = time.time() + 0.04
        start = end = time.time()

        while GPIO.input(echo) == 0:
            start = time.time()
            if start > deadline:
                return 999

        while GPIO.input(echo) == 1:
            end = time.time()
            if end > deadline:
                return 999

        return round((end - start) * 17150, 1)

    def cleanup(self):
        pass
