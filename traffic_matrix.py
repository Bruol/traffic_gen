from __future__ import annotations
import csv
import json
import os

base_dir = os.path.dirname(os.path.realpath(__file__))

class TrafficMatrix():

    _matrix = []
    _timeStepSeconds : int

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
        patterns = []
        for row in self._matrix:
            source_isd = row[0].split("-")[0]
            source_as = row[0].split("-")[1]
            destination_isd = row[1].split("-")[0]
            destination_as = row[1].split("-")[1]
            mode = row[2]

            matrix_start_idx = 3

            for i in range(matrix_start_idx, len(row)):
                start_offset = f"{(i-matrix_start_idx) * self._timeStepSeconds}s"
                patterns.append({
                    "start_offset": start_offset,
                    "source": f"{source_isd}-{source_as}",
                    "destination": f"{destination_isd}-{destination_as}",
                    "mode": mode,
                    "parameters": {
                        "bandwidth": row[i]
                    }
                })
        return patterns




if __name__ == "__main__":
    tm = TrafficMatrix()
    pattern = tm.fromFile(base_dir+"/TrafficMatrix.csv").setTimeStep("10s").toPattern()
    print(json.dumps(pattern, indent=2))