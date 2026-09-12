# VO2max Estimation from Race and Threshold Data

Quick reference for estimating an athlete's VO2max from available performance data when lab testing isn't available.

## Daniels VDOT Method (primary)

VDOT is a pseudo-VO2max derived from race performance. For trained runners, actual lab-tested VO2max typically sits **2-4 points below VDOT**.

### From 5K time

```python
def vdot_from_5k(time_seconds):
    velocity_m_per_min = 5000 / (time_seconds / 60)
    vo2 = velocity_m_per_min * 0.182258 + 0.000104 * (velocity_m_per_min ** 2) - 4.60
    vo2max = vo2 / 0.96  # 5K run at ~96% of VO2max
    return vo2, vo2max
```

**Quick reference table:**

| 5K Time | VDOT | Est. VO2max |
|---------|------|-------------|
| 19:00   | 54   | 50-52       |
| 20:00   | 51   | 47-49       |
| 21:00   | 49   | 45-47       |
| 22:00   | 47   | 43-45       |
| 23:00   | 45   | 41-43       |

### Threshold pace cross-check

Threshold pace should align with VDOT. If threshold is faster than the VDOT table suggests, the athlete may be underperforming in races (tactical, conditions, fatigue) or the VDOT estimate is low.

| VDOT | Threshold (per km) | 5K Race (per km) |
|------|-------------------|------------------|
| 50   | ~4:15-4:20        | ~4:00            |
| 48   | ~4:25-4:30        | ~4:10            |
| 46   | ~4:35-4:40        | ~4:20            |

## Garmin Race Predictor

Garmin's predictor uses VO2max estimate + recent training load. For runners with decent volume, it's usually **directionally correct, sometimes optimistic by 15-30 seconds**.

**How to read it:**
- If Garmin says 20:21 and athlete's threshold pace supports VDOT 48-50, the predictor is in the ballpark
- Race-day boost (taper, adrenaline, competition) typically yields 60-90 seconds faster than in-session efforts
- The gap from threshold to race pace is 10-15 sec/km for well-trained runners

## Concurrent training adjustment

Athletes carrying significant muscle mass (strength training) will show slightly lower ml/kg/min numbers than pure runners at the same performance level. This is because the "kg" in the denominator is higher. The absolute oxygen delivery may be strong even if the relative number looks modest.

**Rule of thumb:** A strength-trained runner at VDOT 50 might test at 48-49 in the lab. A pure runner at the same VDOT might test at 52-54.

## When to use what

| Scenario | Method |
|----------|--------|
| Have recent 5K race | VDOT from race time (most accurate) |
| Have threshold pace only | VDOT from threshold, cross-check with race predictor |
| Have both race and threshold | Use race VDOT, validate with threshold alignment |
| No race data, only training paces | Threshold → VDOT, note higher uncertainty |

## Key caveat

VO2max is the ceiling, but running economy and lactate tolerance are the floor. An athlete with VO2max 49 can run sub-20 if their economy is excellent. An athlete with VO2max 54 might not if their economy is poor. Always pair the number with actual race performance trends.
