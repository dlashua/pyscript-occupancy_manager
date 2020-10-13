import time
import asyncio
import traceback

SHOW_TASK_NAME = False
DEBUG_AS_INFO = False

registered_triggers = []

class OccupancyManager:
    def __init__(self, config):
        if not self.parse_config(config):
            log.error(f'INVALID CONFIG {config}')
            return

        self.log_debug('STARTING')

        self.delay_off_end = 0

        @time_trigger('startup')
        def startup_trigger():
            self.log_info('startup trigger')
            self.clear_delayed_off()
            self.startup()

        registered_triggers.append(startup_trigger)

    def log_id(self):
        if SHOW_TASK_NAME:
            task_name = asyncio.current_task().get_name()
            log_id = f'{self.state_entity} ({task_name})'
        else:
            log_id = f'{self.state_entity}'

        return log_id

    def log_info(self, message):
        log.info(f'{self.log_id()}: {message}')

    def log_error(self, message):
        log.error(f'{self.log_id()}: {message}')

    def log_debug(self, message):
        if DEBUG_AS_INFO:
            log.info(f'{self.log_id()} DEBUG: {message}')
        else:
            log.debug(f'{self.log_id()}: {message}')

    def startup(self):
        self.state = state.get(self.state_entity)
        self.log_info(f'Initial State {self.state}')


        @state_trigger('True or {}'.format(self.state_entity))
        def state_entity_change():
            new_state = state.get(self.state_entity)

            if new_state == self.state:
                return

            self.log_info(f'state entity manually changed from {self.state} to {new_state}')
            self.state = new_state

        registered_triggers.append(state_entity_change)

        if len(self.occupied_conditions) > 0:        
            # Register Occupied Conditions
            @state_trigger('True or {}'.format(" or ".join(self.occupied_conditions)))
            def inner_occupied_condition(**params):
                self.log_info(f'condition change with {params}')
                self.update()

            registered_triggers.append(inner_occupied_condition)        

        if len(self.armed_conditions) > 0:
            # Register Armed Conditions
            @state_trigger('True or {}'.format(" or ".join(self.armed_conditions)))
            def inner_armed_condition(**params):
                self.log_info(f'armed change with {params}')
                self.update()

            registered_triggers.append(inner_armed_condition)  

        if len(self.occupied_states) > 0:
            # Register Occupied States
            @state_trigger('True or {}'.format(" or ".join(self.occupied_states)))
            def inner_occupied_state(**params):
                self.log_info(f'state change with {params}')
                self.update()

            registered_triggers.append(inner_occupied_state)

        if len(self.held_states) > 0:
            # Register Held States
            @state_trigger('True or {}'.format(" or ".join(self.held_states)))
            def inner_held_state(**params):
                self.log_info(f'held change with {params}')
                self.update()

            registered_triggers.append(inner_held_state)


        # Register State Triggers
        for one_state_trigger in self.state_triggers:
            self.log_debug(f'registering trigger {one_state_trigger}')
            
            @state_trigger(one_state_trigger)
            def inner_state_trigger(**params):
                self.log_info(f'state trigger with {params}')
                self.trigger()

            registered_triggers.append(inner_state_trigger)

        # Register Event Trigger
        for one_event_trigger in self.event_triggers:
            if 'expression' in one_event_trigger:
                @event_trigger(one_event_trigger['event'], one_event_trigger['expression'])
                def inner_event_trigger(**params):
                    self.log_info(f'event trigger with {params}')
                    self.trigger()

                registered_triggers.append(inner_event_trigger)
            else:
                @event_trigger(one_event_trigger['event'])
                def inner_event_trigger(**params):
                    self.log_info(f'event trigger with {params}')
                    self.trigger()

                registered_triggers.append(inner_event_trigger)

        @time_trigger('startup')
        def first_update():
            self.log_debug('first update')
            self.update()

        registered_triggers.append(first_update)

    def parse_config(self, data):
        # TODO: use voluptuous
        self.state_entity = data.get('state_entity')
        if self.state_entity is None:
            log.error('state_entity is required')
            return False

        if not self.state_entity.startswith('input_boolean.'):
            log.error('state_entity must be an input_boolean')
            return False

        self.occupied_conditions = data.get('occupied_conditions', [])
        if not isinstance(self.occupied_conditions, list):
            log.error(f'{self.state_entity}: occupied_conditions must be a list')
            return False

        self.occupied_states = data.get('occupied_states', [])
        if not isinstance(self.occupied_states, list):
            log.error(f'{self.state_entity}: occupied_states must be a list')
            return False

        self.armed_conditions = data.get('armed_conditions', [])
        if not isinstance(self.armed_conditions, list):
            log.error(f'{self.state_entity}: armed_conditions must be a list')
            return False

        self.held_states = data.get('held_states', [])
        if not isinstance(self.held_states, list):
            log.error(f'{self.state_entity}: held_states must be a list')
            return False

        self.timeout = data.get('timeout', 0)
        if not isinstance(self.timeout, float) and not isinstance(self.timeout, int):
            log.error(f'{self.state_entity}: timeout must be a float or int')
            return False

        self.state_triggers = data.get('state_triggers', [])
        if not isinstance(self.state_triggers, list):
            log.error(f'{self.state_entity}: state_triggers must be a list')
            return False

        self.event_triggers = data.get('event_triggers', [])
        if not isinstance(self.event_triggers, list):
            log.error(f'{self.state_entity}: event_triggers must be a list')
            return False

        return True

    def get_unique_id(self):
        return f'occupancy_manager_{self.state_entity}'

    def trigger(self):
        self.log_info('TRIGGERED')

        if self.timeout <= 0:
            self.log_error('triggers require a timeout')
            return

        if self.state == 'on':
            self.log_info('already on')
            return

        if not self.check_conditions():
            self.log_info('conditions not met')
            return

        if not self.check_armed():
            self.log_info('not armed')
            return

        self.turn_on()

        # Update after Turn On, because our occupied states/holds are likely not "on"
        # If they aren't "on", this will lead to a "pending_off" state
        self.update()

    def update(self):
        self.log_info('updating')
        if not self.check_conditions():
            self.log_info('conditions not met')
            self.turn_off(immediate=True)
            return

        state = self.check_state()
        armed = self.check_armed()
        held = self.check_held()

        if self.state != 'off' and state:
            self.log_info('not off and state')
            self.turn_on()
            return

        if armed and state:
            self.log_info('armed and state')
            self.turn_on()
            return

        if self.state == 'off' and not armed:
            self.log_info('off and not armed')
            self.turn_off()
            return

        if self.state != 'off' and held:
            self.log_info('not off and held')
            self.turn_on()
            return

        self.turn_off()

    def check_state(self):
        self.log_debug('CHECKING STATE')
        for occupied_state in self.occupied_states:
            try:
                if eval(occupied_state):
                    self.log_debug(f'STATE TRUE {occupied_state}')
                    return True

                self.log_debug(f'STATE FALSE {occupied_state}')
            except NameError as e:
                self.log_error(f'STATE UNKNOWN {occupied_state}')

        self.log_debug('NO STATE TRUE')
        return False

    def check_held(self):
        self.log_debug('CHECKING HELD')
        for held_state in self.held_states:
            try:
                if eval(held_state):
                    self.log_debug(f'HELD TRUE {held_state}')
                    return True

                self.log_debug(f'HELD FALSE {held_state}')
            except NameError as e:
                self.log_error(f'HELD UNKNOWN {held_state}')

        self.log_debug('NO HELD TRUE')
        return False

    def check_conditions(self):
        self.log_debug('CHECKING CONDITIONS')
        for occupied_condition in self.occupied_conditions:
            try:
                if not eval(occupied_condition):
                    self.log_debug(f'CONDITION FALSE {occupied_condition}')
                    return False
                else:
                    self.log_debug(f'CONDITION TRUE {occupied_condition}')
            except NameError as e:
                self.log_error(f'CONDITION UNKNOWN {occupied_condition}')

        self.log_debug(f'ALL CONDITIONS TRUE (or no conditions)')
        return True      

    def check_armed(self):
        self.log_debug('CHECKING ARMED')
        for armed_condition in self.armed_conditions:
            try:
                if not eval(armed_condition):
                    self.log_debug(f'ARMED FALSE {armed_condition}')
                    return False
                else:
                    self.log_debug(f'ARMED TRUE {armed_condition}')
            except NameError as e:
                self.log_error(f'ARMED UNKNOWN {armed_condition}')

        self.log_debug(f'ALL ARMED TRUE (or no armed)')
        return True  

    def turn_on(self):
        if self.state == 'on':
            self.log_info('still on')
            return

        self.clear_delayed_off()

        if self.state == 'pending_off':
            self.log_info('remaining on')
            self.state = 'on'
        else:
            self.log_info('on')
            self.state = 'on'
            input_boolean.turn_on(entity_id=self.state_entity)


    def turn_off(self, immediate=False):
        if self.state == 'off':
            self.log_info('still off')
            return

        if self.timeout == 0:
            immediate = True

        if immediate:
            self.log_info('immediate off')
            self.clear_delayed_off()
            self.state = 'off'
            input_boolean.turn_off(entity_id=self.state_entity)
            return

        self.set_delayed_off()

    def set_delayed_off(self, seconds=None, force=False):
        if force:
            self.clear_delayed_off()

        if seconds is None:
            seconds = self.timeout

        self.log_info('pending off')
        self.state = 'pending_off'

        # Continue Existing Delay
        # Method #1
        self.log_debug('killing myself if there are others')
        task.unique(self.get_unique_id(), kill_me=True)
        self.log_debug('survived')
        # End Method #1

        # Method #2
        # self.log_info('killing others')
        # task.unique(self.get_unique_id())

        # if (self.delay_off_start + seconds) > time.time():
        #     seconds = round(self.delay_off_start + seconds - time.time() + 1)
        #     self.log_info(f'existing delayed off. setting seconds to {seconds}')
        # End Method #2

        self.delay_off_start = time.time()
        self.log_info(f'delay off in {seconds} seconds')

        task.sleep(seconds)

        elapsed = round(time.time() - self.delay_off_start, 2)
        self.log_info(f'delay elapsed in {elapsed}/{seconds} seconds')
        self.turn_off(immediate=True)


    def clear_delayed_off(self):
        self.log_debug(f'clearing delayed off by killing others')
        task.unique(self.get_unique_id())
        self.delay_off_start = 0

##########
# Helpers
##########
factory_apps = []

def load_apps(app_name, factory):
    if "apps" not in pyscript.config:
        return
    
    if app_name not in pyscript.config['apps']:
        return

    for app in pyscript.config['apps'][app_name]:
        factory_apps.append(factory(app))

def load_apps_list(app_name, factory):
    if "apps_list" not in pyscript.config:
        return

    for app in pyscript.config['apps_list']:
        if 'app' in app:
            if app['app'] == app_name:
                factory_apps.append(factory(app))
    

##########
# Startup
##########
@time_trigger('startup')
def load():
    load_apps("occupancy_manager", OccupancyManager)
    load_apps_list('occupancy_manager', OccupancyManager)
