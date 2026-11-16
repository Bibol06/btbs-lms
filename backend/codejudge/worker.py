"""Host process for a capability-restricted WASI interpreter. Never exec user code on the host."""
import json
import sys
import tempfile
from pathlib import Path
import wasmtime


def evaluate(payload):
    config = wasmtime.Config()
    config.consume_fuel = True
    config.cache = True
    config.max_wasm_stack = 512 * 1024
    engine = wasmtime.Engine(config)
    module = wasmtime.Module.from_file(engine, payload['runtime'])
    linker = wasmtime.Linker(engine)
    linker.define_wasi()
    results = []
    for case in payload['cases']:
        stdout, stderr = bytearray(), bytearray()
        truncated = [False]

        def capture(target, limit):
            def write(chunk):
                room = max(0, limit - len(target))
                target.extend(chunk[:room])
                if len(chunk) > room:
                    truncated[0] = True
                return len(chunk)
            return write

        store = wasmtime.Store(engine)
        store.set_limits(memory_size=128 * 1024 * 1024, instances=1, memories=1, table_elements=100000)
        store.set_fuel(300_000_000)
        status = 'ok'
        with tempfile.TemporaryDirectory(prefix='lms-wasi-') as directory:
            stdin = Path(directory) / 'stdin'
            stdin.write_text(case, encoding='utf-8')
            wasi = wasmtime.WasiConfig()
            wasi.argv = ['python', '-I', '-B', '-c', payload['code']]
            wasi.env = [('PYTHONHASHSEED', '0')]
            wasi.stdin_file = str(stdin)
            wasi.stdout_custom = capture(stdout, 8192)
            wasi.stderr_custom = capture(stderr, 4096)
            # No preopened directories, inherited environment, sockets or host callbacks.
            store.set_wasi(wasi)
            try:
                linker.instantiate(store, module).exports(store)['_start'](store)
            except wasmtime.ExitTrap as exc:
                if exc.code:
                    status = 'runtime_error'
            except wasmtime.Trap:
                status = 'limit_exceeded'
            finally:
                store.close()
        if truncated[0]:
            status = 'output_limit'
        results.append({'status': status, 'stdout': stdout.decode('utf-8', errors='replace'), 'stderr': stderr.decode('utf-8', errors='replace')})
    return results


if __name__ == '__main__':
    try:
        payload = json.loads(sys.stdin.buffer.read(500000))
        output = {'results': evaluate(payload)}
    except Exception:
        output = {'error': 'Не удалось запустить изолированную среду Python'}
    sys.stdout.buffer.write(json.dumps(output, ensure_ascii=False).encode('utf-8'))
