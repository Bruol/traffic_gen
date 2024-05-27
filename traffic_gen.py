from seedemu.compiler import Docker
from seedemu.core import Emulator
from seedemu.layers import ScionBase, EtcHosts

from typing import List, Dict, Union, Self

import os
import json

from enum import Enum

import docker

client = docker.from_env()

base_dir = os.path.dirname(os.path.realpath(__file__))


def getContainerByNameAndAS(asn: int, name: str) -> str:
    """
    @brief Get a container by name and AS number
    """
    containers = client.containers.list()
    for container in containers:
        if str(asn) in container.name and name in container.name:
            return container.name

    return None
    


class BWTestServer():
    _port: int
    _asn: int
    _nodeName: str
    _log_file: str
    _command: str = """\
nohup scion-bwtestserver --listen=:{port} >> /var/log/{logfile} 2>&1 &
 """

    def __init__(self, asn: int, port: int = 40002, nodeName: str= "traffic_gen", log_file: str = "bwtestserver.log"):
        self._port = port # default port
        self._asn = asn
        self._nodeName = nodeName
        self._log_file = log_file

    def setPort(self, port: int) -> Self:
        self._port = port
        return self
    
    def getPort(self) -> int:   
        return self._port
    
    def setLogfile(self, log_file: str) -> Self:
        self._log_file = log_file
        return self
    
    def getLogfile(self) -> str:
        return self._log_file
    
    def start(self) -> None:
        """
        @brief Start the server
        """
        container_name = getContainerByNameAndAS(self.asn, self.name)
        if container_name:
            container = client.containers.get(container_name)
            container.exec_run(self._command.format(port=self._port, logfile=self._log_file), detach = True)
        else:
            raise Exception(f"Failed to start BWTestServer on AS{self.asn}. Container not found.")


class BWTestClient():
    _dst_port: int
    _source_asn: int
    _dst_asn: int
    _dst_ip: str
    _cs_str: str
    _sc_str: str
    _nodeName: str
    _log_file: str
    _command: str = """\
nohup scion-bwtestclient -s {server_addr}:{port} -sc {SC} -cs {CS} >> /var/log/{logfile} 2>&1 &
"""
    _resolv_ip_command = """\
getent hosts 111-traffic_gen_111 | awk '{print $1}'
"""

    def __init__(self, source_asn: int, dst_asn: int, dst_port: int = 40002, nodeName: str= "traffic_gen", log_file: str = "bwtestclient.log"):
        self._port = dst_port # default port
        self._source_asn = source_asn
        self._dst_asn = dst_asn
        self._nodeName = nodeName
        self._log_file = log_file





class TrafficMode(Enum):
    BWTESTER = "bwtester"
    IPerf = "iperf"
    IPerf_SIG = "iperf-sig"

class TrafficGenerator():
    _pattern_file: str
    _traffic_pattern: List[Dict[str, Union[str, Dict]]]
    _defaultSoftware: List[str]
    _emu: Emulator

    def __init__(self, pattern_file: str):
        
        self._pattern_file = pattern_file

        with open(self._pattern_file, 'r') as f:
            self._traffic_pattern = json.load(f)
        
        self._defaultSoftware = ["iperf", "net-tools"]

        self._emu = Emulator()


    
    def getTrafficPattern(self) -> List[Dict[str, Union[str, Dict]]]:
        """
        @brief Get the traffic pattern
        """
        return self._traffic_pattern
    
    def _parsePattern(self):
        """
        @brief Parse the traffic pattern
        """
        
    
    def Prepare(self, dump_file: str) -> None:
        """
        @brief Prepare the traffic generator

        @param dump_file: str - The file to dump the traffic generator configuration
        
        creates host to generate traffic, sets up sigs, etc.
        """

        # Load the dump file
        self._emu.load(dump_file)

        # makes node names resolve to ip addresses
        self._emu.addLayer(EtcHosts())

        base: ScionBase = self._emu.getLayer("Base")

        # get set of asses that are need to have a traffic generation node
        ases = []

        for pattern in self._traffic_pattern["traffic_patterns"]:
            
            ases.extend([pattern["source"], pattern["destination"]])

        ases = list(set([int(_as[2:]) for _as in ases]))
        
        # check if ases are already created
        for asn in ases:
            if not base.getAutonomousSystem(asn):
                raise Exception(f"AS{asn} does not exist in seed emulation but is used in a traffic pattern.")

        # Create the traffic generator nodes
        for asn in ases:
            as_ = base.getAutonomousSystem(asn)
            net_name = "net0" # as_.getNetworks()[0]
            generator_host = as_.createHost(f"traffic_gen").joinNetwork(net_name)
            # install software
            [generator_host.addSoftware(software) for software in self._defaultSoftware]
        



    def run(self, output_dir: str = "./seed-compiled") -> None:
        """
        @brief Run the traffic generator
        """
        self._emu.render()
        self._emu.compile(Docker(internetMapEnabled=True), output_dir, override=True)

if __name__ == "__main__":
    # tg = TrafficGenerator("./pattern.json")
    # tg.Prepare("scion-seed.bin")
    # tg.run()
    bt = BWTestServer(110)
    bt.start()