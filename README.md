# occupancy_manager

## What Does it Do?

`occupancy_manager` uses a variety of input sensors (motion sensors, door sensors, device power sensors, etc) as well as event triggers (a light turning on, a door opening, etc) to determine if a room is occupied.

This combines many complicated automations into one simple configuration

## Using it!

This works as an "app" in `pyscript`. Therefore, pyscript is required and configuration is done through Home Assistant's `configuration.yaml` file.

You can see a [full configuration example](config.sample.yaml) in this repository.

These are the configuration keys:

key | description
--- | ---
state_entity (required) | the input_boolean that will be turned on when occupied
occupied_conditions (optional) | a list of pyscript expressions that must ALL be true to allow the room to be occupied
armed_conditions (optional) | a list of pyscript expressions that must ALL be true to allow the room to move to occupied state
occupied_states (optional) | a list of pyscript expressions that AT LEAST ONE must be true to move to occupied state or hold in occupied state 
held_states (optional) | a list of pyscript expressions that AT LEAST ONE must be true to keep the room occupied even if `occupied_states` is False
state_triggers (optional) | a list of pyscript expressions to trigger a momentary "on" state as long as conditions and armed is met
event_triggers (optional) | a list of dicts to trigger a momentary "on" state as long as conditions and armed is met. The dict should contain an `event` key, and, optionally, an `expression` key. 
timeout (optional / required if using triggers) | number of seconds to delay the state from moving to `off` once `occupied_states` and `held_states` are no longer True

If `occupied_conditions` are not met, the `state_entity` will be `off`. `timeout` is not honored so the `off` state will be immediate. An empty list disables `occupied_conditions` checking.

If `armed_conditions` are not met, the `state_entity` cannot change to `on`. An empty list disabled `armed_conditions` checking.

If `occupied_states` are met (along with `occupied_conditions` and `armed_conditions` if set) the `state_entity` will change to `on`. When they are no longer met, the `state_entity` will change to `off` (if `held_states` is not met) honoring the `timeout`.

If `held_states` are met and the `state_entity` is already `on`, it will remain `on`. If they are not met and `occupied_states` is also not met, the `state_entity` will change to `off` honoring the `timeout`.

`state_triggers` are similar to `occupied_states` however, `state_entity` is only set to `on` momentarily. Then it is `off` again, honoring `timeout`. Without a `timeout` this makes no sense and therefore is invalid and will generate an ERROR.

`event_triggers` are similar to `state_triggers` however, the work with Home Assistant events instead of entity states. 


## Requirements

* [PyScript custom_component](https://github.com/custom-components/pyscript)

## Install

### Install this script
```
# get to your homeassistant config directory
cd /config

cd pyscript
mkdir -p apps/
cd apps
git clone https://github.com/dlashua/pyscript-occupancy_manager occupancy_manager
```

### Edit `configuration.yaml`

```yaml
pyscript:
  apps:    
    occupancy_manager:
      - state_entity: input_boolean.living_occupied
        occupied_conditions:
          - binary_sensor.home != 'off'
        armed_conditions:
          - binary_sensor.living_motion_counter == "on"
          - binary_sensor.living_motion_tv == "on"
          - binary_sensor.living_motion_over == "on"
        occupied_states:
          - binary_sensor.living_motion_counter == "on"
          - binary_sensor.living_motion_tv == "on"
          - binary_sensor.living_motion_over == "on"
          - media_player.living_tv == "playing"
        state_triggers:
          - light.living_overhead == 'on' and light.living_overhead.old == 'off'
          - light.living_tv_strip == 'on' and light.living_tv_strip.old == 'off'
        timeout: 600
```

### Reload PyScript
