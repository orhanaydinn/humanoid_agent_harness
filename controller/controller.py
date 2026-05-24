class Controller:
    """
    Supported task types:
        - find_only
        - find_and_pick
        - pick_and_place
    """

    def __init__(self):
        self.allowed_tools = {
            "get_visible_objects",
            "get_robot_status",
            "search_object",
            "pick_object",
            "place_object",
            "stop",
        }

    def decide(self, llm_action, observation):

        if not isinstance(llm_action, dict):
            return self._repair(
                reason="LLM output is not a valid dictionary.",
                repaired_tool="get_robot_status",
                arguments={},
            )

        tool = llm_action.get("tool")
        task_state = observation["task_state"]

        task_type = task_state.get("task_type", "pick_and_place")
        target_object = task_state["target_object"]
        target_location = task_state.get("target_location")
        picked_object = task_state.get("picked_object")
        goal_completed = task_state.get("goal_completed", False)

        visible_objects = {
            obj["id"]: obj
            for obj in observation.get("visible_objects", [])
        }

        target_object_state = visible_objects.get(target_object, {})
        target_location_state = (
            visible_objects.get(target_location, {})
            if target_location
            else {}
        )

        # Goal completed
        if goal_completed:
            return {
                "decision": "DONE",
                "reason": "The goal is already complete.",
                "action": {
                    "type": "tool_call",
                    "response": "Goal complete. Stopping.",
                    "tool": "stop",
                    "arguments": {},
                },
            }

        # Unsupported tool
        if tool not in self.allowed_tools:
            return self._repair(
                reason=f"Unsupported or missing tool requested by LLM: {tool}",
                repaired_tool="get_robot_status",
                arguments={},
            )

        # Early stop
        if tool == "stop" and not goal_completed:
            return self._repair(
                reason="The LLM requested stop before the goal was complete.",
                repaired_tool="get_robot_status",
                arguments={},
            )

        # Task: find_only
        if task_type == "find_only":
            return self._handle_find_only(
                tool=tool,
                target_object=target_object,
                target_object_state=target_object_state,
            )


        # Task: find_and_pick
        if task_type == "find_and_pick":
            return self._handle_find_and_pick(
                tool=tool,
                target_object=target_object,
                target_object_state=target_object_state,
                picked_object=picked_object,
            )


        # Task: pick_and_place
        if task_type == "pick_and_place":
            return self._handle_pick_and_place(
                tool=tool,
                target_object=target_object,
                target_location=target_location,
                target_object_state=target_object_state,
                target_location_state=target_location_state,
                picked_object=picked_object,
            )

        return self._repair(
            reason=f"Unsupported task type: {task_type}. Falling back to robot status.",
            repaired_tool="get_robot_status",
            arguments={},
        )


    # Task handlers
    def _handle_find_only(self, tool, target_object, target_object_state):
        """
        Find-only task:
            Goal is complete when the target object is reachable.
        """

        object_reachable = target_object_state.get("reachable", False)

        if not object_reachable:
            return self._repair(
                reason=(
                    f"{target_object} is not reachable yet. "
                    "Repairing the LLM action into search_object."
                ),
                repaired_tool="search_object",
                arguments={"object": target_object},
            )

        return {
            "decision": "EXECUTE",
            "reason": f"{target_object} is reachable. The find task is complete.",
            "action": {
                "type": "tool_call",
                "response": f"{target_object} found.",
                "tool": "stop",
                "arguments": {},
            },
        }

    def _handle_find_and_pick(self, tool, target_object, target_object_state, picked_object):
        """
        Find-and-pick task:
            First move to the object, then pick it up.
        """

        object_reachable = target_object_state.get("reachable", False)

        if picked_object == target_object:
            return {
                "decision": "DONE",
                "reason": f"{target_object} has already been picked up.",
                "action": {
                    "type": "tool_call",
                    "response": "Goal complete. Stopping.",
                    "tool": "stop",
                    "arguments": {},
                },
            }

        if not object_reachable:
            return self._repair(
                reason=(
                    f"{target_object} is not reachable. "
                    "Repairing the LLM action into search_object."
                ),
                repaired_tool="search_object",
                arguments={"object": target_object},
            )

        if tool != "pick_object":
            return self._repair(
                reason=(
                    f"{target_object} is reachable but has not been picked yet. "
                    "Repairing the LLM action into pick_object."
                ),
                repaired_tool="pick_object",
                arguments={"object": target_object},
            )

        return {
            "decision": "EXECUTE",
            "reason": "The target object is reachable and the pick action is valid.",
            "action": {
                "type": "tool_call",
                "response": f"Picking up {target_object}.",
                "tool": "pick_object",
                "arguments": {
                    "object": target_object,
                },
            },
        }

    def _handle_pick_and_place(
        self,
        tool,
        target_object,
        target_location,
        target_object_state,
        target_location_state,
        picked_object,
    ):
        """
        Pick-and-place task:
            Move to object -> pick object -> move to target location -> place object.
        """

        if not target_location:
            return self._repair(
                reason="No target location was provided for the pick-and-place task.",
                repaired_tool="get_robot_status",
                arguments={},
            )

        object_reachable = target_object_state.get("reachable", False)
        location_reachable = target_location_state.get("reachable", False)

        # Stage 1: the target object must be reached and picked.
        if picked_object is None:
            if not object_reachable:
                return self._repair(
                    reason=(
                        f"{target_object} is not reachable. "
                        "Repairing the LLM action into search_object."
                    ),
                    repaired_tool="search_object",
                    arguments={"object": target_object},
                )

            if tool != "pick_object":
                return self._repair(
                    reason=(
                        f"{target_object} is reachable but not picked yet. "
                        "Repairing the LLM action into pick_object."
                    ),
                    repaired_tool="pick_object",
                    arguments={"object": target_object},
                )

            return {
                "decision": "EXECUTE",
                "reason": "The target object is reachable and the pick action is valid.",
                "action": {
                    "type": "tool_call",
                    "response": f"Picking up {target_object}.",
                    "tool": "pick_object",
                    "arguments": {
                        "object": target_object,
                    },
                },
            }

        # Stage 2: the object is held, so move to the target location.
        if picked_object == target_object:
            if not location_reachable:
                return self._repair(
                    reason=(
                        f"{target_location} is not reachable. "
                        "Repairing the LLM action into search_object."
                    ),
                    repaired_tool="search_object",
                    arguments={"object": target_location},
                )

            if tool != "place_object":
                return self._repair(
                    reason=(
                        f"{target_object} is held and {target_location} is reachable. "
                        "Repairing the LLM action into place_object."
                    ),
                    repaired_tool="place_object",
                    arguments={
                        "object": target_object,
                        "destination": target_location,
                    },
                )

            return {
                "decision": "EXECUTE",
                "reason": (
                    "The place action is valid. Destination was normalised "
                    "to the task target."
                ),
                "action": {
                    "type": "tool_call",
                    "response": f"Placing {target_object} on {target_location}.",
                    "tool": "place_object",
                    "arguments": {
                        "object": target_object,
                        "destination": target_location,
                    },
                },
            }

        return self._repair(
            reason="Unexpected task state. Falling back to robot status.",
            repaired_tool="get_robot_status",
            arguments={},
        )

    # Helpers
    def _repair(self, reason, repaired_tool, arguments): # Creates a repaired executable action


        return {
            "decision": "REPAIR",
            "reason": reason,
            "action": {
                "type": "tool_call",
                "response": reason,
                "tool": repaired_tool,
                "arguments": arguments,
            },
        }