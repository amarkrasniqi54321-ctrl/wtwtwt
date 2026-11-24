"""Compile and run the exact firmware policy on a host C compiler."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CC = shutil.which("cc") or shutil.which("gcc")

@unittest.skipUnless(CC, "host C compiler unavailable")
class CameraPolicyTests(unittest.TestCase):
    def test_policy(self):
        program = r'''
#include <assert.h>
#include "camera_policy.h"
int main(void) {
    camera_policy_t s = {0};
    for (int i=0; i<89; ++i)
        assert(camera_policy_step(&s,0,true,false,90,360).reason==CAMERA_WAKE_NONE);
    assert(camera_policy_step(&s,0,true,false,90,360).reason==CAMERA_WAKE_NORMAL);
    camera_policy_complete(&s,true,90);
    for (int i=0; i<359; ++i)
        assert(camera_policy_step(&s,0,true,false,90,360).reason==CAMERA_WAKE_NONE);
    assert(camera_policy_step(&s,0,true,false,90,360).reason==CAMERA_WAKE_STABLE);
    camera_policy_complete(&s,true,90);
    assert(camera_policy_step(&s,1,true,false,90,360).reason==CAMERA_WAKE_ALARM);
    camera_policy_complete(&s,true,90);
    assert(camera_policy_step(&s,1,true,false,90,360).reason==CAMERA_WAKE_NONE);
    assert(camera_policy_step(&s,3,true,false,90,360).reason==CAMERA_WAKE_ALARM);
    camera_policy_complete(&s,true,90);
    for (int i=0; i<89; ++i)
        assert(camera_policy_step(&s,3,true,false,90,360).reason==CAMERA_WAKE_NONE);
    assert(camera_policy_step(&s,3,true,false,90,360).reason==CAMERA_WAKE_NORMAL);
    camera_policy_complete(&s,true,90);
    assert(camera_policy_step(&s,0,false,true,90,360).reason==CAMERA_WAKE_FAULT);
    camera_policy_complete(&s,false,90);
    assert(camera_policy_step(&s,0,false,true,90,360).reason==CAMERA_WAKE_NORMAL);
    camera_policy_complete(&s,true,90);
    for (int i=0; i<89; ++i)
        assert(camera_policy_step(&s,0,false,false,90,360).reason==CAMERA_WAKE_NONE);
    assert(camera_policy_step(&s,0,false,false,90,360).reason==CAMERA_WAKE_NORMAL);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)/"policy.c"
            out = Path(tmp)/"policy"
            src.write_text(program)
            subprocess.run([CC,"-std=c99","-Wall","-Wextra","-Werror","-I",
                            str(ROOT/"esp32/main"),str(src),"-o",str(out)],check=True)
            subprocess.run([str(out)],check=True)

if __name__ == "__main__":
    unittest.main()
