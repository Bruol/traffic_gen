from __future__ import annotations
import csv
import json
import os

base_dir = os.path.dirname(os.path.realpath(__file__))
#TRAFFIC_MATRIX_FILE = base_dir+"/TrafficMatrix.csv"
TRAFFIC_MATRIX_FILE = base_dir+"/TrafficMatrix_2.csv"
PATTERN_FILE = base_dir+"/pattern_matrix.json"

class TrafficMatrix():

    _matrix = []
    _timeStepSeconds : int = 10

    def __init__(self) -> None:
        pass

    def fromFile(self, file_path: str) -> TrafficMatrix:
        with open(file_path, 'r') as file:
            reader = csv.reader(file)
    
            self._matrix = [row for row in reader][1:]
        return self

    def setTimeStep(self, time_step: str) -> TrafficMatrix:
        if "s" in time_step:
            self._timeStepSeconds = int(time_step.replace("s", ""))
        elif "m" in time_step:
            self._timeStepSeconds = int(time_step.replace("m", "")) * 60
        elif "h" in time_step:
            self._timeStepSeconds = int(time_step.replace("h", "")) * 3600
        return self

    def toPattern(self):
        matrix_start_idx = 4
        source_dest_pair = []
        for row in self._matrix:
            if row[0] == "": # empty source means row refers to previous source
                parameter = row[3]
                source_dest_pair[-1]["parameters"][parameter] = row[matrix_start_idx:]
                continue
            source_isd = row[0].split("-")[0]
            source_as = row[0].split("-")[1]
            destination_isd = row[1].split("-")[0]
            destination_as = row[1].split("-")[1]
            mode = row[2]
            parameter = row[3]


            source_dest_pair.append(
                {
                    "source":  f"{source_isd}-{source_as}",
                    "destination": f"{destination_isd}-{destination_as}",
                    "mode": mode,
                    "parameters": {
                        parameter: row[matrix_start_idx:]
                    }
                }
            )

        patterns = []
        for pattern in source_dest_pair:
            stop_idx = max([len(v) for v in pattern["parameters"].values()])
            for i in range(0, stop_idx):
                start_offset = f"{i * self._timeStepSeconds}s"
                patterns.append({
                    "start_offset": start_offset,
                    "source": pattern["source"],
                    "destination": pattern["destination"],
                    "mode": pattern["mode"],
                    "parameters": {
                        k: v[i] for k, v in pattern["parameters"].items() if i < len(v)
                    }
                })
        # set timestep
        for p in patterns:
            if "duration" not in p["parameters"]:
                p["parameters"]["duration"] = self._timeStepSeconds
            else:
                p["parameters"]["duration"] = int(p["parameters"]["duration"])

        return patterns

    def export(self, file_path: str):
        patterns = self.toPattern()
        export_obj = {
            "traffic_patterns": patterns,
        }
        with open(file_path, 'w') as file:
            json.dump(export_obj, file, indent=4)


if __name__ == "__main__":
    tm = TrafficMatrix()
    tm.fromFile(TRAFFIC_MATRIX_FILE).setTimeStep("10s").export(PATTERN_FILE)

    