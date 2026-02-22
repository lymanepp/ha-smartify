# Smartify

Smartify is a **Home Assistant custom integration** that makes *dumb devices smarter*.

It provides a small, opinionated toolkit of **sensor-driven controllers** that add deterministic, transparent behavior to otherwise simple devices such as:

* lights
* ceiling fans
* exhaust fans

Smartify does **not** attempt to replace Home Assistant automations or scripts. Instead, it focuses on a narrow problem domain:

> **Adding practical, context-aware behavior to individual devices using sensors, timers, and clear rules.**

All behavior is deterministic, explainable, and suitable for **either UI-based or YAML-based configuration**.

---

## Design goals

Smartify is intentionally conservative in scope.

* **Dumb devices stay dumb** — intelligence is layered on top
* **No black boxes** — behavior is rule-based, not heuristic or AI-driven
* **UI and YAML are supported** — configuration may be done via config flow *or* YAML
* **Reusable patterns** — consistent gating, timers, and manual override handling
* **One device at a time** — each controller owns a single device (or tightly related set)

If something looks like a workflow, scene engine, or general automation system, it probably does **not** belong in Smartify.

---

## What Smartify provides

Smartify currently includes controllers for:

### Light controllers

Add intelligence to lights using:

* occupancy or trigger sensors
* optional illuminance gating
* automatic shut-off timers
* manual override windows
* required on/off conditions

Typical use cases:

* closet lights that turn off automatically
* bathroom lights gated by ambient light
* lights that respond to occupancy but respect sleep or guest modes

---

### Ceiling fan controllers

Continuously modulate ceiling fan speed based on environmental conditions.

Features:

* temperature + humidity inputs
* derived comfort index (Summer Simmer Index)
* configurable speed ranges
* hysteresis via min/max thresholds
* manual override windows

Typical use cases:

* living room fans that gently respond to heat and humidity
* bedroom fans that slow or stop when conditions improve

---

### Exhaust fan controllers

Automatically control exhaust fans based on **absolute humidity delta** between rooms.

Features:

* rising / falling thresholds
* reference room comparison
* manual override support

Typical use cases:

* bathroom fans that run only when moisture actually increases
* fans that shut off reliably after showers

---

### Occupancy controllers (supporting / optional)

Occupancy controllers synthesize a binary occupancy sensor from:

* motion sensors
* door sensors
* other related entities

Occupancy controllers exist primarily to **support the other controllers** and may be removed in the future as native sensors improve.

---

## Installation

### Installation via HACS (recommended)

Click the button below to add Smartify as a **custom repository** in HACS:

**Add Smartify to HACS:**
[https://my.home-assistant.io/redirect/hacs_repository/?owner=lymanepp&repository=ha-smartify&category=integration](https://my.home-assistant.io/redirect/hacs_repository/?owner=lymanepp&repository=ha-smartify&category=integration)

After adding the repository:

1. Open **HACS → Integrations**
2. Install **Smartify**
3. Restart Home Assistant
4. Add controllers via the UI **or** YAML

---

### Manual installation

1. Copy the `smartify` directory into your Home Assistant `custom_components` directory:

   ```text
   config/custom_components/smartify/
   ```

2. Restart Home Assistant.

---

## Configuration

Smartify supports **two equal, first-class configuration models**:

* **UI configuration** via Home Assistant’s config flow
* **YAML configuration** for users who prefer explicit, version-controlled setups

You may freely choose either approach, or migrate between them as your setup evolves.

---

## YAML configuration (optional)

If using YAML, configuration is defined under the `smartify:` domain, either inline or via packages.

Recommended setups:

```yaml
smartify: !include smartify.yaml
```

Or using packages:

```yaml
smartify:
  controllers: !include_dir_merge_list smartify/controllers/
```

---

## YAML configuration examples

```yaml
smartify:
  controllers:

    # Light controller example
    - type: light
      controlled_entity: light.master_bedroom_light
      trigger_entity: binary_sensor.master_bedroom_occupancy
      auto_off_minutes: 5
      manual_control_minutes: 30
      illuminance_sensor: sensor.master_bedroom_ambient_illuminance
      illuminance_cutoff: 70
      required_off_entities:
        - binary_sensor.any_sleeping

    # Ceiling fan controller example
    - type: ceiling_fan
      controlled_entity: fan.living_room_fan
      temp_sensor: sensor.living_room_temperature
      humidity_sensor: sensor.living_room_relative_humidity
      ssi_min: 81.0
      ssi_max: 91.0
      speed_min: 25
      speed_max: 75
      manual_control_minutes: 60
      required_on_entities:
        - binary_sensor.living_room_occupancy

    # Exhaust fan controller example
    - type: exhaust_fan
      controlled_entity: fan.guest_bathroom_fan
      temp_sensor: sensor.guest_bathroom_temperature
      humidity_sensor: sensor.guest_bathroom_relative_humidity
      reference_temp_sensor: sensor.living_room_temperature
      reference_humidity_sensor: sensor.living_room_relative_humidity
      rising_threshold: 2.0
      falling_threshold: 0.5
      manual_control_minutes: 15

    # Occupancy controller example
    - type: occupancy
      sensor_name: "Office Occupancy"
      motion_sensors:
        - binary_sensor.office_motion
      motion_off_minutes: 10
      other_entities:
        - media_player.office_tv
      required_on_entities:
        - binary_sensor.home_occupancy
```

---

## Philosophy

Smartify exists in the space *between*:

* simple on/off automations, and
* large, opaque "smart" systems.

It favors:

* clarity over cleverness
* explicit configuration over inference
* boring reliability over novelty

Whether configured through the UI or YAML, Smartify aims to make device behavior **predictable, inspectable, and intentional**.

---

## Status

Smartify is a personal custom integration and may evolve over time. Backward compatibility is valued, but configuration remains explicit by design.

Contributions and experimentation are welcome — just keep the scope tight.
