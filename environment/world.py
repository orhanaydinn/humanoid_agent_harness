import copy


class VirtualPickPlaceWorld:
    """
    Supported task types:
        - find_only:
            The goal is complete when the target object becomes reachable.

        - find_and_pick:
            The goal is complete when the target object is picked up.

        - pick_and_place:
            The goal is complete when the target object is placed on the target location.

    The agent always starts at [0, 0].
    """

    def __init__(
        self,
        goal=None,
        target_object="target_object",
        target_location=None,
        object_position=None,
        location_position=None,
        task_type="pick_and_place",
    ):
        self.agent_position = [0, 0]
        self.inventory = []

        self.target_object = target_object
        self.target_location = target_location
        self.task_type = task_type

        # Pick-and-place tasks need a placement target.
        # Find-only and find-and-pick tasks can work without one.
        if self.task_type == "pick_and_place" and self.target_location is None:
            self.target_location = "target_location"

        # Build a generic goal if one is not provided.
        if goal is None:
            if self.task_type == "find_only":
                goal = f"Find the {self.target_object}."
            elif self.task_type == "find_and_pick":
                goal = f"Find the {self.target_object} and pick it up."
            else:
                goal = (
                    f"Pick up the {self.target_object} "
                    f"and place it on the {self.target_location}."
                )

        self.goal = goal

        object_position = object_position or [2, 1]
        location_position = location_position or [4, 4]

        self.objects = {
            self.target_object: {
                "id": self.target_object,
                "type": "object",
                "color": self._infer_color(self.target_object),
                "position": list(object_position),
                "held": False,
                "placed_on": None,
            }
        }

        # Keep target location in the world only when it exists.
        # This allows find_only and find_and_pick tasks to stay simple.
        if self.target_location:
            self.objects[self.target_location] = {
                "id": self.target_location,
                "type": "surface",
                "color": self._infer_color(self.target_location),
                "position": list(location_position),
            }

        self.step_count = 0

    def _infer_color(self, object_id): # check color


        object_id = str(object_id).lower()

        known_colors = [
            "red",
            "blue",
            "green",
            "yellow",
            "black",
            "white",
            "orange",
            "purple",
            "brown",
            "grey",
            "gray",
        ]

        for color in known_colors:
            if color in object_id:
                return color

        return "unknown"

    def manhattan_distance(self, a, b): # Calculate to distance in the 2D world


        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def is_reachable(self, object_id):


        obj = self.objects.get(object_id)

        if obj is None:
            return False

        return self.manhattan_distance(self.agent_position, obj["position"]) == 0

    def goal_completed(self): # check current task status


        target = self.objects[self.target_object]

        if self.task_type == "find_only":
            return self.is_reachable(self.target_object)

        if self.task_type == "find_and_pick":
            return (
                target["held"] is True
                and self.target_object in self.inventory
            )

        if self.task_type == "pick_and_place":
            return (
                target["held"] is False
                and target["placed_on"] == self.target_location
                and self.target_object not in self.inventory
            )

        return False

    # Observation
    def get_visible_objects(self): # Returns structured object information for the agent.

        visible_objects = []

        for object_id, obj in self.objects.items():
            item = copy.deepcopy(obj)

            item["distance"] = self.manhattan_distance(
                self.agent_position,
                obj["position"],
            )

            item["reachable"] = self.is_reachable(object_id)

            visible_objects.append(item)

        return visible_objects

    def get_observation(self):

        picked_object = self.inventory[0] if self.inventory else None

        return {
            "goal": self.goal,
            "step": self.step_count,
            "task_type": self.task_type,
            "agent": {
                "position": list(self.agent_position),
                "inventory": list(self.inventory),
            },
            "visible_objects": self.get_visible_objects(),
            "task_state": {
                "task_type": self.task_type,
                "target_object": self.target_object,
                "target_location": self.target_location,
                "picked_object": picked_object,
                "goal_completed": self.goal_completed(),
            },
            "available_tools": [
                "get_visible_objects",
                "get_robot_status",
                "search_object",
                "pick_object",
                "place_object",
                "stop",
            ],
        }

    def execute(self, action): # Executes a validated action.
        self.step_count += 1

        tool = action.get("tool")
        arguments = action.get("arguments", {}) or {}

        if tool == "get_visible_objects":
            return {
                "success": True,
                "message": "Visible objects returned.",
                "observation": self.get_observation(),
            }

        if tool == "get_robot_status":
            return {
                "success": True,
                "message": "Robot status returned.",
                "status": {
                    "agent_position": list(self.agent_position),
                    "inventory": list(self.inventory),
                    "task_type": self.task_type,
                    "goal_completed": self.goal_completed(),
                },
            }

        if tool == "search_object":
            object_id = (
                arguments.get("object")
                or arguments.get("object_id")
                or arguments.get("target_id")
                or arguments.get("destination")
                or arguments.get("location")
            )

            return self._move_to(object_id)

        if tool == "pick_object":
            object_id = arguments.get("object") or arguments.get("object_id")
            return self._pick_object(object_id)

        if tool == "place_object":
            object_id = arguments.get("object") or arguments.get("object_id")

            destination = (
                arguments.get("destination")
                or arguments.get("target_id")
                or arguments.get("location")
            )

            return self._place_object(object_id, destination)

        if tool == "stop":
            if self.goal_completed():
                return {
                    "success": True,
                    "message": "Stopped. Goal completed.",
                }

            return {
                "success": False,
                "message": "Stopped before completing the goal.",
            }

        return {
            "success": False,
            "message": f"Unsupported tool: {tool}",
        }

    # Tool implementations
    def _move_to(self, object_id):

        if object_id not in self.objects:
            return {
                "success": False,
                "message": f"Cannot search for unknown object: {object_id}",
            }
    
        target = self.objects[object_id]
        self.agent_position = list(target["position"])
    
        if self.task_type == "find_only" and object_id == self.target_object:
            message = f"Agent searched for {object_id} and found it."
    
        elif object_id == self.target_object:
            message = f"Agent searched for {object_id} and moved to its location."
    
        elif object_id == self.target_location:
            message = f"Agent moved to the target location: {object_id}."
    
        else:
            message = f"Agent moved to {object_id}."
    
        return {
            "success": True,
            "message": message,
            "agent_position": list(self.agent_position),
        }

    def _pick_object(self, object_id):
        """
        Picks up the target object if it is reachable.
        """

        if object_id not in self.objects:
            return {
                "success": False,
                "message": f"Cannot pick unknown object: {object_id}",
            }

        if object_id == self.target_location:
            return {
                "success": False,
                "message": f"{self.target_location} cannot be picked up.",
            }

        if self.inventory:
            return {
                "success": False,
                "message": f"Inventory already contains {self.inventory[0]}.",
            }

        if not self.is_reachable(object_id):
            return {
                "success": False,
                "message": f"{object_id} is not reachable.",
            }

        obj = self.objects[object_id]
        obj["held"] = True
        obj["placed_on"] = None

        self.inventory.append(object_id)

        return {
            "success": True,
            "message": f"Picked up {object_id}.",
        }

    def _place_object(self, object_id, destination):
        """
        Places the held object on the destination.
        """

        if object_id not in self.inventory:
            return {
                "success": False,
                "message": f"Cannot place {object_id}; it is not in inventory.",
            }

        if not destination:
            return {
                "success": False,
                "message": "No destination was provided.",
            }

        if destination not in self.objects:
            return {
                "success": False,
                "message": f"Unknown destination: {destination}",
            }

        if destination != self.target_location:
            return {
                "success": False,
                "message": (
                    f"Invalid destination for this task: {destination}. "
                    f"Expected: {self.target_location}."
                ),
            }

        if not self.is_reachable(destination):
            return {
                "success": False,
                "message": f"{destination} is not reachable.",
            }

        obj = self.objects[object_id]

        obj["held"] = False
        obj["placed_on"] = destination
        obj["position"] = list(self.objects[destination]["position"])

        self.inventory.remove(object_id)

        return {
            "success": True,
            "message": f"Placed {object_id} on {destination}.",
        }