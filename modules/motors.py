"""DC Motor (L298N) + Servo head control."""
import time
import threading

try:
    import RPi.GPIO as GPIO
    _HW = True
except ImportError:
    _HW = False
    print("[MOTOR] RPi.GPIO not found — simulation mode")

import config
from config import RobotState


class MotorController:
    def __init__(self, shared_state, sensor=None):
        self.shared = shared_state
        self.sensor = sensor
        self.speed = config.DEFAULT_SPEED
        self._patrol_running = False
        self._follow_running = False

        if _HW:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for pin in [config.MOTOR_IN1, config.MOTOR_IN2,
                        config.MOTOR_IN3, config.MOTOR_IN4]:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, False)

            GPIO.setup(config.MOTOR_ENA, GPIO.OUT)
            GPIO.setup(config.MOTOR_ENB, GPIO.OUT)
            self.pwm_a = GPIO.PWM(config.MOTOR_ENA, 1000)
            self.pwm_b = GPIO.PWM(config.MOTOR_ENB, 1000)
            self.pwm_a.start(0)
            self.pwm_b.start(0)

            GPIO.setup(config.SERVO_PIN, GPIO.OUT)
            self.servo = GPIO.PWM(config.SERVO_PIN, 50)
            self.servo.start(0)

        print("[MOTOR] Ready")

    # ── basic moves ──────────────────────────
    def _set_pwm(self):
        if _HW:
            self.pwm_a.ChangeDutyCycle(self.speed)
            self.pwm_b.ChangeDutyCycle(self.speed)

    def forward(self, t=0):
        if not _HW: return
        self._set_pwm()
        GPIO.output(config.MOTOR_IN1, 1); GPIO.output(config.MOTOR_IN2, 0)
        GPIO.output(config.MOTOR_IN3, 1); GPIO.output(config.MOTOR_IN4, 0)
        if t > 0: time.sleep(t); self.stop()

    def backward(self, t=0):
        if not _HW: return
        self._set_pwm()
        GPIO.output(config.MOTOR_IN1, 0); GPIO.output(config.MOTOR_IN2, 1)
        GPIO.output(config.MOTOR_IN3, 0); GPIO.output(config.MOTOR_IN4, 1)
        if t > 0: time.sleep(t); self.stop()

    def turn_left(self, t=0):
        if not _HW: return
        self._set_pwm()
        GPIO.output(config.MOTOR_IN1, 0); GPIO.output(config.MOTOR_IN2, 1)
        GPIO.output(config.MOTOR_IN3, 1); GPIO.output(config.MOTOR_IN4, 0)
        if t > 0: time.sleep(t); self.stop()

    def turn_right(self, t=0):
        if not _HW: return
        self._set_pwm()
        GPIO.output(config.MOTOR_IN1, 1); GPIO.output(config.MOTOR_IN2, 0)
        GPIO.output(config.MOTOR_IN3, 0); GPIO.output(config.MOTOR_IN4, 1)
        if t > 0: time.sleep(t); self.stop()

    def stop(self):
        if not _HW: return
        for p in [config.MOTOR_IN1, config.MOTOR_IN2,
                  config.MOTOR_IN3, config.MOTOR_IN4]:
            GPIO.output(p, 0)
        self.pwm_a.ChangeDutyCycle(0)
        self.pwm_b.ChangeDutyCycle(0)

    def set_speed(self, s):
        self.speed = max(0, min(100, s))

    # ── servo head ───────────────────────────
    def servo_angle(self, angle):
        if not _HW: return
        angle = max(0, min(180, angle))
        duty = 2 + (angle / 18)
        self.servo.ChangeDutyCycle(duty)
        time.sleep(0.3)
        self.servo.ChangeDutyCycle(0)

    # ── patrol (obstacle avoidance) ──────────
    def start_patrol(self):
        if self._patrol_running:
            return
        self._patrol_running = True
        threading.Thread(target=self._patrol_loop, daemon=True).start()

    def stop_patrol(self):
        self._patrol_running = False
        self.stop()

    def _patrol_loop(self):
        print("[MOTOR] 🚗 Patrol started")
        voice = self.shared.modules.get("voice")
        while self._patrol_running and self.shared.state == RobotState.PATROL:
            if self.sensor:
                d = self.sensor.get_distance()
                self.shared.obstacle_distance = d
                if d < config.OBSTACLE_DISTANCE:
                    print(f"[MOTOR] ⚠️ Obstacle at {d:.0f}cm! Changing direction")
                    self.stop()
                    if voice:
                        try:
                            voice.speak(f"Obstacle detected at {d:.0f} centimeters! Changing direction!")
                        except: pass
                    time.sleep(0.2)
                    self.backward(0.5)
                    self.turn_right(0.7)
                else:
                    self.forward()
            time.sleep(0.1)
        self.stop()
        print("[MOTOR] 🛑 Patrol stopped")

    # ── follow face ──────────────────────────
    def start_follow(self):
        if self._follow_running:
            return
        self._follow_running = True
        threading.Thread(target=self._follow_loop, daemon=True).start()

    def stop_follow(self):
        self._follow_running = False
        self.stop()

    def _follow_loop(self):
        """Move toward detected face until close enough."""
        print("[MOTOR] Following face")
        while self._follow_running and self.shared.state == RobotState.FOLLOWING:
            face = self.shared.face_position
            if face is None:
                self.stop()
                time.sleep(0.2)
                continue

            fx, fy, fw, fh = face
            cx = fx + fw // 2
            area = fw * fh

            if cx < 240:
                self.turn_left(0.15)
            elif cx > 400:
                self.turn_right(0.15)
            elif area < config.FACE_CLOSE_AREA:
                self.forward(0.2)
            else:
                self.stop()
                self._follow_running = False
                print("[MOTOR] Reached person")
                break
            time.sleep(0.1)
        self.stop()

    # ── cleanup ──────────────────────────────
    def cleanup(self):
        self.stop_patrol()
        self.stop_follow()
        self.stop()
        if _HW:
            self.pwm_a.stop()
            self.pwm_b.stop()
            self.servo.stop()
