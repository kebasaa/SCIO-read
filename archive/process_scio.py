import json
import base64
import struct
import math
import ast

def decode_hex_to_floats(hex_str):
    bytes_data = bytes.fromhex(hex_str)
    num_floats = len(bytes_data) // 4
    floats = struct.unpack('<' + 'f' * num_floats, bytes_data)
    return list(floats)

def moving_average(data, window_size):
    result = []
    sum_val = 0.0
    for i in range(len(data)):
        sum_val += data[i]
        if i >= window_size:
            avg = sum_val / window_size
            sum_val -= data[i - window_size]
            result.append(avg)
    return result

def derivative(vector, ignore2bytes):
    result = []
    for i in range(2, len(vector) - 2):
        val = (1.0 * vector[i-2] - 8.0 * vector[i-1] + 0.0 * vector[i] + 8.0 * vector[i+1] - 1.0 * vector[i+2]) / 12.0
        result.append(val)
    return result  # ignore2bytes=true, so no padding

def process_spectrum(reflectance):
    # ln
    ln_spec = [math.log(r) for r in reflectance]
    # avgWindow(35)
    avg_spec = moving_average(ln_spec, 35)
    # derivative(true)
    deriv_spec = derivative(avg_spec, True)
    # subtract avg
    mean_deriv = sum(deriv_spec) / len(deriv_spec)
    final_spec = [d - mean_deriv for d in deriv_spec]
    return final_spec

# Load JSON
with open('<USER_HOME>/Documents/Linux/scio/data_scans/scan_from_log_20200604_144021.json', 'r') as f:
    data = json.load(f)

sample_hex = data['raw_data']['sample'][:2960]  # 370 floats * 4 bytes * 2 hex chars = 2960

sample = decode_hex_to_floats(sample_hex)

print(f"Sample length: {len(sample)}")
print(f"First 10 sample: {sample[:10]}")

spec = process_spectrum(sample)
print(f"Processed length: {len(spec)}")
print(f"First 10 processed: {spec[:10]}")

# Compare to spec_data
spec_data = ast.literal_eval(data['spec_data'])
print(f"Spec data length: {len(spec_data)}")
print(f"First 10 spec_data: {spec_data[:10]}")
close = all(abs(a - b) < 1e-3 for a, b in zip(spec, spec_data))
print(f"Match: {close}")