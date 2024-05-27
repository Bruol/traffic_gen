from __future__ import annotations
from seedemu.compiler import Docker
from seedemu.core import Emulator
from seedemu.layers import ScionBase, EtcHosts

from typing import List, Dict, Union

import time
from datetime import datetime

import os
import json

from enum import Enum

from python_on_whales import DockerClient


base_dir = os.path.dirname(os.path.realpath(__file__))



def getContainerByNameAndAS(asn: int, name: str) -> str:
    """
    @brief Get a container by name and AS number
    """
    docker = DockerClient(compose_files=[base_dir+"/seed-compiled/docker-compose.yml"])
    containers = docker.ps()
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
bash -c "scion-bwtestserver --listen=:{port} >> /var/log/traffic_gen/{logfile}"\
"""
    _docker: DockerClient

    def __init__(self, asn: int, port: int = 40002, nodeName: str= "traffic_gen", log_file: str = "bwtestserver.log", docker: DockerClient = DockerClient(compose_files=[base_dir+"/seed-compiled/docker-compose.yml"])):
        self._port = port # default port
        self._asn = asn
        self._nodeName = nodeName
        self._log_file = log_file
        self._docker = docker

    def setPort(self, port: int) -> BWTestServer:
        self._port = port
        return self
    
    def getPort(self) -> int:   
        return self._port
    
    def setLogfile(self, log_file: str) -> BWTestServer:
        self._log_file = log_file
        return self
    
    def getLogfile(self) -> str:
        return self._log_file
    
    def start(self) -> None:
        """
        @brief Start the server
        """
        container = getContainerByNameAndAS(self._asn, self._nodeName)
        if container:
            self._docker.execute(container, ["/bin/bash","-c",self._command.format(port=self._port, logfile=self._log_file)], detach = True)
        else:
            raise Exception(f"Failed to start BWTestServer on AS{self.asn}. Container not found.")


class BWTestClient():
    _dst_port: int
    _source_asn: int
    _dst_asn: int
    _dst_isd: int
    _dst_ip: str
    _cs_str: str = ""
    _sc_str: str = ""
    _src_node_name: str
    _dst_node_name: str
    _log_file: str
    _docker: DockerClient
    _command: str = """\
scion-bwtestclient -s {server_addr}:{port} {SC} {CS} >> /var/log/traffic_gen/{logfile}\
"""
    _resolv_ip_command = "/usr/bin/getent hosts {hostname}"


    def __init__(self, source_asn: int, dst_isd: int, dst_asn: int, dst_port: int = 40002, src_node_name: str= "traffic_gen", dst_node_name: str= "traffic_gen", log_file: str = "bwtestclient.log", docker: DockerClient = DockerClient(compose_files=[base_dir+"/seed-compiled/docker-compose.yml"])):
        self._port = dst_port # default port
        self._source_asn = source_asn
        self._dst_asn = dst_asn
        self._src_node_name = src_node_name
        self._dst_node_name = dst_node_name
        self._log_file = log_file
        self._dst_isd = dst_isd
        self._docker = docker
        self._dst_ip = ""

    def setPort(self, port: int) -> BWTestClient:
        self._port = port
        return self

    def getPort(self) -> int:
        return self._port

    def setLogfile(self, log_file: str) -> BWTestClient:
        self._log_file = log_file
        return self
    
    def getLogfile(self) -> str:
        return self._log_file
    
    def setCS(self, cs: str) -> BWTestClient:
        self._cs_str = "-cs " + cs
        return self
    
    def getCS(self) -> str: 
        return self._cs_str.replace("-cs ", "")
    
    def setSC(self, sc: str) -> BWTestClient:
        self._sc_str = "-sc " + sc
        return self
    
    def getSC(self) -> str:
        return self._sc_str.replace("-sc ", "")
    
    def start(self) -> None:
        """
        @brief Start the client
        """
        container = getContainerByNameAndAS(self._source_asn, self._src_node_name)
        if container:
            dst_hostname = f"{self._dst_asn}-{self._dst_node_name}"
            self._dst_ip = self._docker.execute(container, ["/bin/bash","-c",self._resolv_ip_command.format(hostname=dst_hostname)]).split(" ")[0]
            cmd = self._command.format(server_addr=f"{self._dst_isd}-{self._dst_asn},{self._dst_ip}", port=self._port, SC=self._sc_str, CS=self._cs_str, logfile=self._log_file)
            self._docker.execute(container, ["/bin/bash","-c",cmd], detach = True)
        else:
            raise Exception(f"Failed to start BWTestClient on AS{self._source_asn}. Container not found.")




class TrafficMode(Enum):
    BWTESTER = "bwtester"
    IPerf = "iperf"
    IPerf_SIG = "iperf-sig"

class TrafficGenerator():
    _pattern_file: str
    _traffic_pattern: List[Dict[str, Union[str, Dict]]]
    _defaultSoftware: List[str]
    _emu: Emulator
    _wait_for_up: int = 30
    _occupied_ports: Dict[int, int]

    def __init__(self, pattern_file: str):
        
        self._pattern_file = pattern_file

        with open(self._pattern_file, 'r') as f:
            self._traffic_pattern = json.load(f)
        
        self._defaultSoftware = ["iperf", "net-tools"]

        self._emu = Emulator()

        self._occupied_ports = {}



    
    def getTrafficPattern(self) -> List[Dict[str, Union[str, Dict]]]:
        """
        @brief Get the traffic pattern
        """
        return self._traffic_pattern
    
    def _parsePattern(self):
        """
        @brief Parse the traffic pattern
        """
        # convert start offset to seconds
        for pattern in self._traffic_pattern["traffic_patterns"]:
            if "s" in pattern["start_offset"]:
                offset = int(pattern["start_offset"].replace("s", ""))
                pattern["start_offset"] = offset
            elif "m" in pattern["start_offset"]:
                offset = int(pattern["start_offset"].replace("m", "")) * 60
                pattern["start_offset"] = offset
            elif "h" in pattern["start_offset"]:
                offset = int(pattern["start_offset"].replace("h", "")) * 60 * 60
                pattern["start_offset"] = offset
            else:  
                raise Exception("Invalid start_offset format. Must be in seconds, minutes or hours.")
        
        # order the patterns by start_offset
        self._traffic_pattern["traffic_patterns"] = sorted(self._traffic_pattern["traffic_patterns"], key=lambda x: x["start_offset"])

        return

    def _createLogFolder(self, base_dir: str, asn: int, override: bool=True) -> str:
        """
        @brief Create the log folder
        """

        if not os.path.exists(base_dir+"/logs"):
            os.makedirs(base_dir+"/logs")
        
        if not os.path.exists(base_dir+f"/logs/AS{asn}"):
            os.makedirs(base_dir+f"/logs/AS{asn}")
        else:
            if not override:
                raise Exception(f"Log folder for AS{asn} already exists.")
            else:
                os.system(f"rm -rf {base_dir}/logs/AS{asn}")
                os.makedirs(base_dir+f"/logs/AS{asn}")
        
        return base_dir+f"/logs/AS{asn}"
    
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

        # initialize the occupied ports
        for asn in ases:
            self._occupied_ports[asn] = 40001 # start from 40002 and increment by 1 for each new server

        
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
            # set log dirs
            log_folder = self._createLogFolder(base_dir, asn)
            generator_host.addSharedFolder("/var/log/traffic_gen/", log_folder)
    
    def _setUpBWTester(self, pattern: Dict[str, Union[str, Dict]], pattern_id: int) -> tuple[BWTestServer, BWTestClient]:
        """
        @brief Set up the BWTester
        """
        
        dest_asn = int(pattern["destination"].split("-")[1])

        port = self._occupied_ports[dest_asn]+1
        self._occupied_ports[dest_asn] = port

        btserver = BWTestServer(dest_asn, port, log_file=f"bwtestserver_{str(pattern_id)}.log")
     

        source_asn = int(pattern["source"].split("-")[1])
        dst_isd = int(pattern["destination"].split("-")[0])

        btclient = BWTestClient(source_asn, dst_isd, dest_asn, port, log_file=f"bwtestclient_{str(pattern_id)}.log")
        
        if "cs" in pattern["parameters"]:
            btclient.setCS(pattern["parameters"]["cs"])
        if "sc" in pattern["parameters"]:
            btclient.setSC(pattern["parameters"]["sc"])

        
        return btserver, btclient

        

    def run(self, output_dir: str = base_dir+"/seed-compiled") -> None:
        """
        @brief Run the traffic generator
        """
        self._parsePattern()

        self._emu.render()
        self._emu.compile(Docker(internetMapEnabled=True), output_dir, override=True)
            
        docker = DockerClient(compose_files=[output_dir+"/docker-compose.yml"])

        #docker.compose.build()
        docker.compose.up(detach=True)  

        
        print(f"\n\n\nWaiting {self._wait_for_up} seconds for Containers to be ready\n\n\n")
        time.sleep(self._wait_for_up)   

        print("Starting Traffic Generation")
        offset_accumulator = 0
        pattern_id = 0

        # iterate through patterns which are ordered by start_offset
        # TODO: add support for iperf and iperf-sig
        # TODO: add progress bar
        for pattern in self._traffic_pattern["traffic_patterns"]:
            
            time.sleep(pattern["start_offset"]-offset_accumulator)
            offset_accumulator += pattern["start_offset"]
            

            if pattern["mode"] == TrafficMode.BWTESTER.value:
                
                btserver, btclient = self._setUpBWTester(pattern, pattern_id)

                print(f"generating traffic from AS{pattern['source']} to AS{pattern['destination']}")

                btserver.start()
                btclient.start()
            
            elif pattern["mode"] == TrafficMode.IPerf.value:
                pass
            elif pattern["mode"] == TrafficMode.IPerf_SIG.value:
                pass
            else:
                raise Exception(f"Invalid mode {pattern['mode']}")

            pattern_id += 1



        print("Traffic Generation Completed")




if __name__ == "__main__":
    tg = TrafficGenerator(base_dir+"/pattern_sample.json")
    tg.Prepare(base_dir+"/scion-seed.bin")
    tg.run()
