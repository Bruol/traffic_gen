from __future__ import annotations
from seedemu.compiler import Docker
from seedemu.core import Emulator
from seedemu.layers import ScionBase, EtcHosts, Scion, Ebgp, PeerRelationship, ScionIsd, Ibgp
from seedemu.layers.Scion import LinkType

from typing import List, Dict, Union

import time
from datetime import datetime

import os
import json
import shutil


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
    
class Server():
    _port: int
    _asn: int
    _nodeName: str
    _log_file: str
    _command: str
    _docker: DockerClient
    _name: str

    def __init__(self, asn: int, port: int = 40002, nodeName: str= "traffic_gen", log_file: str = "server.log", docker: DockerClient = DockerClient(compose_files=[base_dir+"/seed-compiled/docker-compose.yml"])) -> None:
        self._port = port
        self._asn = asn
        self._nodeName = nodeName
        self._log_file = log_file
        self._docker = docker
    
    def setPort(self, port: int) -> Server:
        self._port = port
        return self
    
    def getPort(self) -> int:
        return self._port
    
    def setLogfile(self, log_file: str) -> Server:
        self._log_file = log_file
        return self
    
    def getLogfile(self) -> str:
        return self._log_file
    
    def setName(self, name: str) -> Server:
        self._name = name
        return self
    
    def getName(self) -> str:
        return self._name

    def start(self) -> None:
        """
        @brief Start the server
        """
        raise NotImplementedError("Method not implemented")

class Client():
    _dst_port: int
    _source_asn: int
    _dst_asn: int
    _dst_isd: int
    _dst_ip: str
    _src_node_name: str
    _dst_node_name: str
    _log_file: str
    _docker: DockerClient
    _command: str
    _resolv_ip_command: str = "/usr/bin/getent hosts {hostname}"
    _name: str

    def __init__(self, source_asn: int, dst_isd: int, dst_asn: int, dst_port: int = 40002, src_node_name: str= "traffic_gen", dst_node_name: str= "traffic_gen", log_file: str = "client.log", docker: DockerClient = DockerClient(compose_files=[base_dir+"/seed-compiled/docker-compose.yml"])) -> None:
        self._port = dst_port
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

    def setName(self, name: str) -> Server:
        self._name = name
        return self
    
    def getName(self) -> str:
        return self._name
    
    def _getDstIP(self, container) -> str:
        dst_hostname = f"{self._dst_asn}-{self._dst_node_name}"
        self._dst_ip = self._docker.execute(container, ["/bin/bash","-c",self._resolv_ip_command.format(hostname=dst_hostname)]).split(" ")[0]
        return self._dst_ip

class IPerfServer(Server):

    def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._name = "iperfserver"
            self._command = """\
iperf3 -s -p {port} > /var/log/traffic_gen/{logfile}\
"""

    def start(self) -> None:
        container = getContainerByNameAndAS(self._asn, self._nodeName)
        if container:
            self._docker.execute(container, ["/bin/bash","-c",self._command.format(port=self._port, logfile=self._log_file)], detach = True)
        else:
            raise Exception(f"Failed to start IPerfServer on AS{self.asn}. Container not found.")

    
class IPerfClient(Client):
    _bandwidth: str = ""
    _packet_size: str = ""
    _duration: int = ""
    _transmit_size: str = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = "iperfclient"
        self._command = """\
iperf3 -c {server_addr} -p {port} -b {bandwidth} -l {packet_size} -t {duration} -n {transmit_size} > /var/log/traffic_gen/{logfile}\
"""
    def setBandwidth(self, bandwidth: str) -> IPerfClient:
        self._bandwidth = bandwidth
        return self
    
    def getBandwidth(self) -> str:
        return self._bandwidth
    
    def setPacketSize(self, packet_size: str) -> IPerfClient:
        self._packet_size = packet_size
        return self
    
    def getPacketSize(self) -> str:
        return self._packet_size
    
    def setDuration(self, duration: int) -> IPerfClient:
        self._duration = duration
        return self
    
    def getDuration(self) -> int:
        return self._duration
    
    def setTransmitSize(self, transmit_size: str) -> IPerfClient:
        self._transmit_size = transmit_size
        return self

    def getTransmitSize(self) -> str:
        return self._transmit_size

    def start(self) -> None:
        container = getContainerByNameAndAS(self._source_asn, self._src_node_name)
        if container:
            ip = self._getDstIP(container)
            cmd = self._command.format(server_addr=ip, 
                                       port=self._port, 
                                       bandwidth = self._bandwidth, 
                                       packet_size = self._packet_size, 
                                       duration = self._duration, 
                                       transmit_size = self._transmit_size, 
                                       logfile=self._log_file)
            self._docker.execute(container, ["/bin/bash","-c",cmd], detach = True)
        else:
            raise Exception(f"Failed to start BWTestClient on AS{self._source_asn}. Container not found.")

class BWTestServer(Server):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = "bwtestserver"
        self._command = """\
bash -c "scion-bwtestserver --listen=:{port} >> /var/log/traffic_gen/{logfile}"\
"""
    
    def start(self) -> None:
        """
        @brief Start the server
        """
        container = getContainerByNameAndAS(self._asn, self._nodeName)
        if container:
            self._docker.execute(container, ["/bin/bash","-c",self._command.format(port=self._port, logfile=self._log_file)], detach = True)
        else:
            raise Exception(f"Failed to start BWTestServer on AS{self.asn}. Container not found.")

class BWTestClient(Client):

    _cs_str: str
    _sc_str: str

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = "bwtestclient"
        self._cs_str = ""
        self._sc_str = ""
        self._command = """\
scion-bwtestclient -s {server_addr}:{port} {SC} {CS} >> /var/log/traffic_gen/{logfile}\
"""
    
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
            ip = self._getDstIP(container)
            cmd = self._command.format(server_addr=f"{self._dst_isd}-{self._dst_asn},{ip}", port=self._port, SC=self._sc_str, CS=self._cs_str, logfile=self._log_file)
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
    _enable_bgp: bool = True
    _wait_for_down: int = 10

    def __init__(self, pattern_file: str):
        
        self._pattern_file = pattern_file

        with open(self._pattern_file, 'r') as f:
            self._traffic_pattern = json.load(f)
        
        self._defaultSoftware = ["iperf3", "net-tools"]

        self._emu = Emulator()

        self._occupied_ports = {}


    def _zip_logs(self, log_folder: str = base_dir + "/logs", output_dir: str = "./logs"):  
        """
        @brief Zip the log files
        """
        shutil.make_archive(output_dir, 'zip', log_folder)
        return output_dir+".zip"

    
    def _addBGP(self):
        """
        @brief get scion routes and translate them to equivalent bgp routes

        @note adds an AS that is a BGP router for CORE-ASes
        """

        scion: Scion = self._emu.getLayer("Scion")
        base : ScionBase = self._emu.getLayer("Base")
        scion_isd : ScionIsd = self._emu.getLayer("ScionIsd")
        
        ix = base.createInternetExchange(100)

        isd = max(base.getIsolationDomains()) + 1 # get the first ISD we dont need this as this AS will not be part of SCION network

        bgp_router_asn = max(base.getAsns()) + 1
        bgp_router = base.createAutonomousSystem(bgp_router_asn)
        scion_isd.addIsdAs(isd, bgp_router_asn, is_core=True)
        bgp_router.createNetwork('net0')
        bgp_router.createRouter('router0').joinNetwork('net0').joinNetwork('ix100')
    

        ebgp = Ebgp()

        links = scion.getXcLinks()

        for link in links:
            a_asn = link[0].asn
            b_asn = link[1].asn
            link_type = str(link[4])
            if link_type == "Transit":
                bgp_type = PeerRelationship.Provider
            elif link_type == "Peering":
                bgp_type = PeerRelationship.Peer
            else: # handle CORE peering
                bgp_type = PeerRelationship.Peer
                # add bgp router as a Provider to all CORE ASes to ensure connectivity
                ebgp.addPrivatePeering(bgp_router_asn, a_asn, PeerRelationship.Provider)
                ebgp.addPrivatePeering(bgp_router_asn, b_asn, PeerRelationship.Provider)
            
            ebgp.addCrossConnectPeering(a_asn, b_asn, bgp_type)

        self._emu.addLayer(ebgp)
        self._emu.addLayer(Ibgp()) # add ibgp to ensure connectivity between all ASes

        
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

        # determine how long to wait after last pattern was started
        for pattern in self._traffic_pattern["traffic_patterns"]:
            if pattern["mode"] == TrafficMode.BWTESTER.value:
                sc_duration = int(pattern["parameters"]["sc"].split(",")[0]) if "sc" in pattern["parameters"] else 3
                cs_duration = int(pattern["parameters"]["cs"].split(",")[0]) if "cs" in pattern["parameters"] else 3
                duration = max(sc_duration, cs_duration)
            elif pattern["mode"] == TrafficMode.IPerf.value:
                duration = pattern["parameters"]["duration"] if "duration" in pattern["parameters"] else 10
            self._wait_for_down = max(self._wait_for_down, duration + 10)
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
    
        # add bgp
        if self._enable_bgp:
            self._addBGP()

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

    def _setUpIPerf(self, pattern: Dict[str, Union[str, Dict]], pattern_id: int) -> tuple[IPerfServer, IPerfClient]:
        """
        @brief Set up the IPerf
        """
        
        dest_asn = int(pattern["destination"].split("-")[1])

        port = self._occupied_ports[dest_asn]+1
        self._occupied_ports[dest_asn] = port

        ipserver = IPerfServer(dest_asn, port, log_file=f"IperfServer_{str(pattern_id)}.log")
     

        source_asn = int(pattern["source"].split("-")[1])
        dst_isd = int(pattern["destination"].split("-")[0])

        ipclient = IPerfClient(source_asn, dst_isd, dest_asn, port, log_file=f"IperfClient_{str(pattern_id)}.log")
        
        if "bandwidth" in pattern["parameters"]:
            ipclient.setBandwidth(pattern["parameters"]["bandwidth"])
        if "packet_size" in pattern["parameters"]:
            ipclient.setPacketSize(pattern["parameters"]["packet_size"])
        if "duration" in pattern["parameters"]:
            ipclient.setDuration(pattern["parameters"]["duration"])
        if "transmit_size" in pattern["parameters"]:
            ipclient.setTransmitSize(pattern["parameters"]["transmit_size"])
        
        return ipserver, ipclient
        
    def _generate_patterns(self):

        print("Starting Traffic Generation")
        old_offset = 0
        pattern_id = 0
        
        # iterate through patterns which are ordered by start_offset
        # TODO: add support for iperf and iperf-sig
        # TODO: add progress bar
        for pattern in self._traffic_pattern["traffic_patterns"]:
            
            time.sleep(pattern["start_offset"]-old_offset)
            old_offset = pattern["start_offset"]
            

            if pattern["mode"] == TrafficMode.BWTESTER.value:
                
                btserver, btclient = self._setUpBWTester(pattern, pattern_id)

                print(f"generating BWTESTER traffic from AS{pattern['source']} to AS{pattern['destination']}")

                btserver.start()
                btclient.start()
            
            elif pattern["mode"] == TrafficMode.IPerf.value:
                ipserver, ipclient = self._setUpIPerf(pattern, pattern_id)

                print(f"generating IPERF traffic from AS{pattern['source']} to AS{pattern['destination']}")

                ipserver.start()
                ipclient.start()
            elif pattern["mode"] == TrafficMode.IPerf_SIG.value:
                pass
            else:
                raise Exception(f"Invalid mode {pattern['mode']}")

            pattern_id += 1

        print("Traffic Generation Completed\n\n")

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


        self._generate_patterns()

        print(f"Waiting for {self._wait_for_down} seconds for traffic generation to finish")
        time.sleep(self._wait_for_down)
        docker.compose.down()
        
        print("Zipping Logs")
        self._zip_logs()




if __name__ == "__main__":
    tg = TrafficGenerator(base_dir+"/pattern_sample.json")
    tg.Prepare(base_dir+"/scion-seed.bin")
    tg.run()
