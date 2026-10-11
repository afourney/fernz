"""Shared V5 startup assertions and public-reference measurements."""

from .vector_archive import digest


def object_memory(data):
    # The pinned 9:05 build lays out all objects/properties between its object
    # table and global variables. Read the addresses directly from the header.
    # This deliberately excludes host capability fields and parser scratch.
    start = int.from_bytes(data[0x0A:0x0C], "big")
    end = int.from_bytes(data[0x0C:0x0E], "big")
    assert start == 0x10A and end == 0x10A5
    return data[start:end]


def capture_reference(env, action, observation):
    return {
        "action": action,
        "observation_sha256": digest(observation.replace("\r\n", "\n").encode()),
        "object_memory_sha256": digest(object_memory(env.get_state()[0].tobytes())),
    }


def check_step(env, record):
    response = env.reset() if record["action"] is None else env.step(record["action"])
    observation = response[0].replace("\r\n", "\n")
    # Public Jericho omits the opening's first blank line, the input newline,
    # and this story's precise trailing prompt. Preserve all other whitespace.
    assert observation.startswith("\n") and observation.endswith("\n\n>")
    assert digest(observation[1:-3].encode()) == record["observation_sha256"]
    assert digest(object_memory(env.get_state().ram)) == record["object_memory_sha256"]
    return response
