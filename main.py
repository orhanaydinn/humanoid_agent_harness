import argparse
import re
from pathlib import Path

from environment.world import VirtualPickPlaceWorld
from controller.controller import Controller
from agent.hf_agent import HuggingFaceAgent

# Goal parsing
def parse_goal(goal_text):
    text = goal_text.lower().strip()
    text = text.replace(".", "").replace(",", "")

    if not text:
        raise ValueError("Goal is empty.")

    place_keywords = [
        "place",
        "put",
        "drop",
        "move",
        "bring",
        "carry",
        "transfer",
    ]

    pick_keywords = [
        "pick up",
        "pick",
        "grab",
        "get",
        "take",
    ]

    find_keywords = [
        "find",
        "locate",
        "search for",
        "look for",
        "where is",
        "where's",
    ]

    has_place_intent = any(keyword in text for keyword in place_keywords)
    has_pick_intent = any(keyword in text for keyword in pick_keywords)
    has_find_intent = any(keyword in text for keyword in find_keywords)

    if has_place_intent:
        task_type = "pick_and_place"
    elif has_pick_intent:
        task_type = "find_and_pick"
    elif has_find_intent:
        task_type = "find_only"
    else:
        raise ValueError("Could not detect a supported task type.")

    target_location = None

    if task_type == "pick_and_place":
        location_match = re.search(
            r"(?:on|in|into|onto|to|near)\s+(?:the\s+)?([a-zA-Z0-9_\- ]+)$",
            text,
        )

        if not location_match:
            raise ValueError("Could not detect the target location.")

        target_location_raw = location_match.group(1).strip()

        if "table" in target_location_raw:
            target_location = "table"
        elif "box" in target_location_raw:
            target_location = "box"
        elif "shelf" in target_location_raw:
            target_location = "shelf"
        elif "tray" in target_location_raw:
            target_location = "tray"
        else:
            target_location = target_location_raw.replace(" ", "_")

    object_match = None

    if task_type == "pick_and_place":
        object_match = re.search(
            r"(?:pick up|pick|grab|get|take|move|bring|carry|transfer)\s+"
            r"(?:the\s+)?([a-zA-Z0-9_\- ]+?)"
            r"(?:\s+and|\s+to|\s+on|\s+in|\s+into|\s+onto|\s+near|\s+place|\s+put|\s+drop|$)",
            text,
        )

    elif task_type == "find_and_pick":
        object_match = re.search(
            r"(?:find|locate|search for|look for|pick up|pick|grab|get|take)\s+"
            r"(?:the\s+)?([a-zA-Z0-9_\- ]+?)"
            r"(?:\s+and|\s+then|\s+pick|\s+grab|\s+take|$)",
            text,
        )

    elif task_type == "find_only":
        object_match = re.search(
            r"(?:find|locate|search for|look for|where is|where's)\s+"
            r"(?:the\s+)?([a-zA-Z0-9_\- ]+)$",
            text,
        )

    if not object_match:
        raise ValueError("Could not detect the target object.")

    target_object = object_match.group(1).strip()

    if not target_object:
        raise ValueError("Target object is empty.")

    target_object = target_object.replace(" ", "_")

    return target_object, target_location, task_type

# Interactive setup
def ask_position(label):
    while True:
        raw = input(f"{label} location x y (0-10): ").strip()
        parts = raw.replace(",", " ").split()

        if len(parts) != 2:
            print("Please enter two numbers, example: 2 4", flush=True)
            continue

        try:
            x = int(parts[0])
            y = int(parts[1])
        except ValueError:
            print("Please enter valid integer numbers.", flush=True)
            continue

        if not (0 <= x <= 10 and 0 <= y <= 10):
            print("Both values must be between 0 and 10.", flush=True)
            continue

        return [x, y]


def build_world_from_user_input():
    print("\nInteractive scenario setup", flush=True)
    print("=" * 60, flush=True)

    while True:
        goal = input("What is the goal?: ").strip()

        try:
            target_object, target_location, task_type = parse_goal(goal)
            break

        except ValueError as error:
            print(f"\nCould not parse the goal: {error}", flush=True)
            print("Please try one of these formats:", flush=True)
            print("- find the bottle", flush=True)
            print("- locate the cup", flush=True)
            print("- pick the key", flush=True)
            print("- find the phone and pick it up", flush=True)
            print("- pick the bottle and place it on the table", flush=True)
            print("- move the apple to the basket\n", flush=True)

    print(f"Detected task type: {task_type}", flush=True)
    print(f"Detected target object: {target_object}", flush=True)

    if target_location:
        print(f"Detected target location: {target_location}", flush=True)
    else:
        print("Detected target location: not required for this task", flush=True)

    print("Agent start location is fixed at [0, 0].", flush=True)

    object_position = ask_position(target_object)

    if task_type == "pick_and_place":
        location_position = ask_position(target_location)
    else:
        location_position = None

    return VirtualPickPlaceWorld(
        goal=goal,
        target_object=target_object,
        target_location=target_location,
        object_position=object_position,
        location_position=location_position,
        task_type=task_type,
    )

# Simple logging helpers
def action_to_text(action):
    if not isinstance(action, dict):
        return "invalid_action"

    tool = action.get("tool")
    args = action.get("arguments", {}) or {}

    if "raw_output" in args:
        return f"{tool}(raw_output=[hidden])"

    if not args:
        return f"{tool}()"

    args_text = ", ".join(f"{key}={value}" for key, value in args.items())
    return f"{tool}({args_text})"


def get_object(observation, object_id):
    if not object_id:
        return None

    for obj in observation.get("visible_objects", []):
        if obj.get("id") == object_id:
            return obj

    return None


def state_line(observation):
    task_state = observation["task_state"]
    agent = observation["agent"]

    target_object_id = task_state.get("target_object")
    target_location_id = task_state.get("target_location")

    target_object = get_object(observation, target_object_id)
    target_location = get_object(observation, target_location_id)

    parts = [
        f"agent={agent.get('position')}",
        f"inventory={agent.get('inventory')}",
    ]

    if target_object:
        parts.append(
            f"{target_object_id}=pos{target_object.get('position')}, "
            f"dist={target_object.get('distance')}, "
            f"reachable={target_object.get('reachable')}"
        )

    if target_location:
        parts.append(
            f"{target_location_id}=pos{target_location.get('position')}, "
            f"dist={target_location.get('distance')}, "
            f"reachable={target_location.get('reachable')}"
        )

    return " | ".join(parts)


def write_log(logs, text=""):
    print(text, flush=True)
    logs.append(text)


def log_step(logs, step, observation_before, llm_action, controller_decision, world_result, observation_after):
    write_log(logs, "")
    write_log(logs, f"Step {step}")
    write_log(logs, "-" * 60)

    write_log(logs, f"Before: {state_line(observation_before)}")
    write_log(logs, f"LLM: {action_to_text(llm_action)}")

    decision = controller_decision.get("decision")
    selected_action = action_to_text(controller_decision.get("action"))

    if decision == "REPAIR":
        write_log(
            logs,
            f"Controller: REPAIR | corrected LLM tool -> {selected_action}"
        )
    elif decision == "EXECUTE":
        write_log(
            logs,
            f"Controller: EXECUTE | LLM tool accepted -> {selected_action}"
        )
    elif decision == "DONE":
        write_log(
            logs,
            f"Controller: DONE | task already completed -> {selected_action}"
        )
    else:
        write_log(
            logs,
            f"Controller: {decision} -> {selected_action}"
        )
    write_log(logs, f"World: {world_result.get('message')}")
    write_log(logs, f"After: {state_line(observation_after)}")

# Main loop
def run(max_steps=8, verbose_model=False, interactive=True):
    logs = []

    if interactive:
        world = build_world_from_user_input()
    else:
        world = VirtualPickPlaceWorld()

    controller = Controller()

    write_log(logs, "")
    write_log(logs, "Loading LLM agent...")
    agent = HuggingFaceAgent(verbose=verbose_model)

    write_log(logs, "")
    write_log(logs, "Humanoid Agent Harness Demo")
    write_log(logs, "=" * 60)
    write_log(logs, f"Goal: {world.goal}")
    write_log(logs, f"Task type: {world.task_type}")
    write_log(logs, "Design: LLM proposes actions; Controller validates or repairs; World updates state.")

    for step in range(1, max_steps + 1):
        observation_before = world.get_observation()

        if observation_before["task_state"]["goal_completed"]:
            break

        write_log(logs, "")
        write_log(logs, f"Running step {step}...")

        llm_action = agent.act(observation_before)

        controller_decision = controller.decide(
            llm_action,
            observation_before,
        )

        executable_action = controller_decision["action"]
        world_result = world.execute(executable_action)

        observation_after = world.get_observation()

        log_step(
            logs=logs,
            step=step,
            observation_before=observation_before,
            llm_action=llm_action,
            controller_decision=controller_decision,
            world_result=world_result,
            observation_after=observation_after,
        )

        if observation_after["task_state"]["goal_completed"]:
            write_log(logs, "")
            write_log(logs, "Final result: SUCCESS - Goal completed.")
            write_log(logs, f"Final state: {state_line(observation_after)}")
            break

    else:
        write_log(logs, "")
        write_log(logs, "Final result: FAILED - Max steps reached before goal completion.")

    examples_dir = Path("examples")
    examples_dir.mkdir(exist_ok=True)

    output_path = examples_dir / "successful_run.txt"
    output_path.write_text("\n".join(logs), encoding="utf-8")

    write_log(logs, "")
    print(f"Saved readable run log to: {output_path}", flush=True)

# CLI
def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--max-steps",
        type=int,
        default=8,
        help="Maximum number of agent-environment loop steps.",
    )

    parser.add_argument(
        "--verbose-model",
        action="store_true",
        help="Print raw model outputs for debugging.",
    )

    parser.add_argument(
        "--default",
        action="store_true",
        help="Run a default generic scenario without interactive input.",
    )

    args = parser.parse_args()

    run(
        max_steps=args.max_steps,
        verbose_model=args.verbose_model,
        interactive=not args.default,
    )


if __name__ == "__main__":
    main()