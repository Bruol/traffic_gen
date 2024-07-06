from __future__ import annotations
from typing import List, Dict, Union, Tuple
from enum import Enum
# SeedEmu imports
from seedemu.compiler import Docker
from seedemu.core import Emulator, Binding, ScionAutonomousSystem, Filter
from seedemu.layers import ScionBase, EtcHosts, Scion, Ebgp, PeerRelationship, ScionIsd, Ibgp
from seedemu.services import ScionSIGService
# Python imports
import time
import os
import json
import shutil
import signal
from functools import partial
import argparse
# Docker imports
from python_on_whales import DockerClient
# Traffic Matrix Support
from traffic_matrix import TrafficMatrix



base_dir = os.path.dirname(os.path.realpath(__file__))


# this handles pressing ctrl+c
def handler( tg: TrafficGenerator = None, *args):
    print("\n\nYou pressed Ctrl+C - stopping emulation")
    if tg:
        tg.stop()
    exit(0)

def getContainerByNameAndAS(asn: int, name: str) -> str:
    """
    @brief Get a container by name and AS number
    """
    docker = DockerClient()
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

    def __init__(self, asn: int, port: int = 50002, nodeName: str= "traffic_gen", log_file: str = "server.log", docker: DockerClient = DockerClient()) -> None:
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
    _args: List[str]

    def __init__(self, source_asn: int, dst_isd: int, dst_asn: int, dst_port: int = 50002, src_node_name: str= "traffic_gen", dst_node_name: str= "traffic_gen", log_file: str = "client.log", docker: DockerClient = DockerClient()) -> None:
        self._port = dst_port
        self._source_asn = source_asn
        self._dst_asn = dst_asn
        self._src_node_name = src_node_name
        self._dst_node_name = dst_node_name
        self._log_file = log_file
        self._dst_isd = dst_isd
        self._docker = docker
        self._dst_ip = ""
        self._args = []

    def appendArgs(self, arg: str, value: str) -> Client:
        self._args.append(f"-{arg} {value}")
        return self
    
    def getArgs(self) -> List[str]:
        return self._args

    def setPort(self, port: int) -> Client:
        self._port = port
        return self

    def getPort(self) -> int:
        return self._port

    def setLogfile(self, log_file: str) -> Client:
        self._log_file = log_file
        return self
    
    def getLogfile(self) -> str:
        return self._log_file

    def setName(self, name: str) -> Client:
        self._name = name
        return self
    
    def getName(self) -> str:
        return self._name
    
    def setDstIP(self, dst_ip: str) -> Client:
        self._dst_ip = dst_ip
        return self
    
    def getDstIP(self) -> str:
        return self._dst_ip
    
    def getDstIPDynamicially(self, container) -> str:
        dst_hostname = f"{self._dst_asn}-{self._dst_node_name}"
        self._dst_ip = self._docker.execute(container, ["/bin/bash","-c",self._resolv_ip_command.format(hostname=dst_hostname)]).split(" ")[0]
        return self._dst_ip

class IPerfServer(Server):

    def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._name = "iperfserver"
            self._command = """\
iperf3 -s -p {port} --logfile /var/log/traffic_gen/{logfile}\
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
    _duration: str = ""
    _transmit_size: str = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = "iperfclient"
        self._command = """\
iperf3 --logfile /var/log/traffic_gen/{logfile} -c {server_addr} -p {port} {bandwidth} {packet_size} {duration} {transmit_size} {args}\
"""
    def setBandwidth(self, bandwidth: str) -> IPerfClient:
        self._bandwidth = "-b " + bandwidth
        return self
    
    def getBandwidth(self) -> str:
        return self._bandwidth.replace("-b", "")
    
    def setPacketSize(self, packet_size: str) -> IPerfClient:
        self._packet_size = "-l" + packet_size
        return self
    
    def getPacketSize(self) -> str:
        return self._packet_size.replace("-l", "")
    
    def setDuration(self, duration: int) -> IPerfClient:
        self._duration = "-t " + str(duration)
        return self
    
    def getDuration(self) -> int:
        return self._duration.replace("-t ", "")
    
    def setTransmitSize(self, transmit_size: str) -> IPerfClient:
        self._transmit_size = "-n " + transmit_size
        return self

    def getTransmitSize(self) -> str:
        return self._transmit_size.replace("-n ", "")

    def start(self) -> None:
        container = getContainerByNameAndAS(self._source_asn, self._src_node_name)
        if container:
            if self._dst_ip == "":
                ip = self.getDstIPDynamicially(container)
            else:
                ip = self._dst_ip
            cmd = self._command.format(server_addr=ip, 
                                       port=self._port, 
                                       bandwidth = self._bandwidth, 
                                       packet_size = self._packet_size, 
                                       duration = self._duration, 
                                       transmit_size = self._transmit_size, 
                                       logfile=self._log_file,
                                       args=" ".join(self._args))
            self._docker.execute(container, ["/bin/bash","-c",cmd],detach=True)
        else:
            raise Exception(f"Failed to start BWTestClient on AS{self._source_asn}. Container not found.")

class BWTestServer(Server):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = "bwtestserver"
        self._command = "scion-bwtestserver --listen=:{port} > /var/log/traffic_gen/{logfile} 2>&1 &"
    
    def start(self) -> None:
        """
        @brief Start the server
        """
        container = getContainerByNameAndAS(self._asn, self._nodeName)
        if container:
            cmd = self._command.format(port=self._port, logfile=self._log_file)
            self._docker.execute(container, ["/bin/bash","-c",cmd], detach = True)
            return
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
scion-bwtestclient -s {server_addr}:{port} {SC} {CS} {args} > /var/log/traffic_gen/{logfile} 2>&1 &\
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
            ip = self.getDstIPDynamicially(container)
            cmd = self._command.format(server_addr=f"{self._dst_isd}-{self._dst_asn},{ip}", port=self._port, SC=self._sc_str, CS=self._cs_str, logfile=self._log_file, args=" ".join(self._args))
            self._docker.execute(container, ["/bin/bash","-c",cmd], detach = True)
        else:
            raise Exception(f"Failed to start BWTestClient on AS{self._source_asn}. Container not found.")

class WebServer(Server):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = "webserver"
        self._command = """\
sed -i 's/\ERROR_LOG/{error_log}/g' /etc/nginx/nginx.conf && sed -i 's/\ACCESS_LOG/{access_log}/g' /etc/nginx/nginx.conf && nginx -c /etc/nginx/nginx.conf\
"""

    def start(self) -> None:
        container = getContainerByNameAndAS(self._asn, self._nodeName)
        if container:
            cmd = self._command.format(access_log=f"access_{self._log_file}", error_log=f"error_{self._log_file}")
            self._docker.execute(container, ["/bin/bash","-c",cmd], detach = True)
        else:
            raise Exception(f"Failed to start WebServer on AS{self.asn}. Container not found.")

class WebClient(Client):
    _duration: int

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = "webclient"
        self._command = """\
python3 /app/web_client.py --url http://{server_addr} --duration {duration} --logfile /var/log/traffic_gen/{logfile} {args}\
"""
# wget -O /dev/null -o /var/log/traffic_gen/{logfile} --spider --recursive {server_addr} 2>&1 &\
        self._duration = 60

    def setDuration(self, duration: int) -> WebClient:
        self._duration = duration
        return self
    
    def getDuration(self) -> int:
        return self._duration

    def start(self) -> None:
        container = getContainerByNameAndAS(self._source_asn, self._src_node_name)
        if container:
            if self._dst_ip == "":
                ip = self.getDstIPDynamicially(container)
            else:
                ip = self._dst_ip
            cmd = self._command.format(server_addr=ip, 
                                       duration=self._duration,
                                       logfile=self._log_file,
                                       args=" ".join(self._args))
            res = self._docker.execute(container, ["/bin/bash","-c",cmd],detach=True)
        else:
            raise Exception(f"Failed to start WEB Client on AS{self._source_asn}. Container not found.")

        return 
    
class TrafficMode(Enum):
    BWTESTER = "bwtester"
    IPerf = "iperf"
    web = "web"

class TrafficGenerator():
    _pattern_file: str
    _traffic_pattern: List[Dict[str, Union[str, Dict]]]
    _defaultSoftware: List[str] 
    _emu: Emulator
    _wait_for_up: int
    _occupied_ports: Dict[int, int]
    _enable_bgp: bool = True # TODO: disable this if no ipv4 applications in pattern
    _custom_webpages: str = None
    _logDir: str
    _seedCompileDir: str
    _webpage_dir: str = base_dir+"/webpages"

    def __init__(self, pattern_file: str, wait_for_up: int, logDir: str, seedCompileDir: str):
        
        self._pattern_file = pattern_file

        with open(self._pattern_file, 'r') as f:
            self._traffic_pattern = json.load(f)
        
        self._defaultSoftware = ["iperf3", "net-tools", "python3", "python3-pip"]

        self._emu = Emulator()

        self._occupied_ports = {}

        self._wait_for_up = wait_for_up

        self._logDir = os.path.abspath(logDir)

        self._seedCompileDir = seedCompileDir

    def zip_logs(self, output_dir: str = "./logs"):  
        """
        @brief Zip the log files
        """
        shutil.make_archive(output_dir, 'zip', self._logDir)
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
            else: # handle core links later
                continue

            peerings = ebgp.getCrossConnectPeerings()
            if (b_asn,a_asn) in peerings or (a_asn,b_asn) in peerings: # if we have already added this link as a peer, skip
                continue

            ebgp.addCrossConnectPeering(a_asn, b_asn, bgp_type)

        # Handle Core links
        for asn in base.getAsns():
            # get isds for AS
            isds = scion_isd.getAsIsds(asn)
            # is AS core in any ISD
            core = [ iscore for (_,iscore) in isds]
            # if so add ebgp to bgp_router
            if (not asn == bgp_router_asn) and (True in core):
                as_ = base.getAutonomousSystem(asn)
                as_.createRouter(f'bgp_router_{asn}').joinNetwork('net0').joinNetwork('ix100')
                ebgp.addPrivatePeering(100, bgp_router_asn, asn, PeerRelationship.Provider)   

        self._emu.addLayer(ebgp)
        self._emu.addLayer(Ibgp()) # add ibgp to ensure connectivity between all ASes
        
    def setCustomWebPages(self, webpages: str) -> TrafficGenerator:
        """
        @brief Set the path to file with custom webpages
        """
        self._custom_webpages = webpages
        return self

    def setWebpageDir(self, webpage_dir: str) -> TrafficGenerator:
        """
        @brief Set the directory to clone webpages to
        """
        self._webpage_dir = webpage_dir
        return self

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

    def _createLogFolder(self, asn: int, override: bool=True) -> str:
        """
        @brief Create the log folder
        """

        if not os.path.exists(self._logDir):
            os.makedirs(self._logDir)
        
        if not os.path.exists(self._logDir + f"/AS{asn}"):
            os.makedirs(self._logDir+f"/AS{asn}")
        else:
            if not override:
                raise Exception(f"Log folder for AS{asn} already exists.")
            else:
                os.system(f"rm -rf {self._logDir}/AS{asn}")
                os.makedirs(self._logDir+f"/AS{asn}")
        
        return self._logDir+f"/AS{asn}"
    
    def _prepareSIGs(self):
        """
        @brief add sigs to traffic_gen nodes that need them
        """
        supported_modes = [TrafficMode.IPerf.value, TrafficMode.web.value]

        sig_patterns = [pattern for pattern in self._traffic_pattern["traffic_patterns"] if (pattern["mode"] in supported_modes and "sig" in pattern and pattern["sig"] == True)]

        if not sig_patterns:
            return
        
        base: ScionBase = self._emu.getLayer("Base")

        sig = ScionSIGService()

        sig_net = "172.16.{network}.0/24"
        network_index = 1

        # assign networks

        asns = list(set([pattern["source"].split("-")[1] for pattern in sig_patterns] + [pattern["destination"].split("-")[1] for pattern in sig_patterns]))

        networks: Dict[int, str] = {} # {asn: network}

        for as_ in asns:
            as_ = int(as_)
            networks[as_] = sig_net.format(network=network_index)
            network_index += 1

        # parse connections to create configurations

        other_datastructure: Dict[str,List[Tuple[int,int,str]]] = {} # {source_asn: [(dst_isd, dst_asn, dst_net)]}

        for pattern in sig_patterns:
            source_as = int(pattern["source"].split("-")[1])
            source_isd = int(pattern["source"].split("-")[0])
            dest_as = int(pattern["destination"].split("-")[1])
            dest_isd = int(pattern["destination"].split("-")[0])
            source_net = networks[source_as]
            dst_net = networks[dest_as]

            if source_as in other_datastructure:
                other_datastructure[source_as].append((dest_isd, dest_as, dst_net))
            else:
                other_datastructure[source_as] = [(dest_isd, dest_as, dst_net)]

            if dest_as in other_datastructure:
                other_datastructure[dest_as].append((source_isd, source_as, source_net))
            else:
                other_datastructure[dest_as] = [(source_isd, source_as, source_net)]

            # set dst_ip in traffic pattern    
            pattern["dst_ip"] = dst_net.replace("0/24", "1")



        for asn in other_datastructure:

            
            # set up source

            source_asn = asn
            source_as: ScionAutonomousSystem = base.getAutonomousSystem(source_asn)
            source_network_index = int(networks[source_asn].split(".")[2])
            source_node = source_as.createHost(f"sig{source_network_index}").joinNetwork("net0")


            source_as.setSigConfig(sig_name = f"sig{source_network_index}", 
                                   node_name=f"sig{source_network_index}", 
                                   local_net = networks[source_asn],
                                   other=other_datastructure[asn])

            sig.install(f"sig{source_network_index}").setConfig(f"sig{source_network_index}", source_as.getSigConfig(f"sig{source_network_index}"))

            self._emu.addBinding(Binding(f"sig{source_network_index}", filter=Filter(nodeName=f"sig{source_network_index}", asn=source_asn)))




        self._emu.addLayer(sig)

        return

    def _cloneWebPages(self,webpages: List[str]) -> None:
        """
        @brief Clone the web pages
        """

        index_template = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Links Landing</title>
</head>
<body>
    <h1>Links to Subdirectory</h1>
{links}
</body>
</html>

"""

        link_template = '<p><a href="{link}">{title}</a></p>\n'
        

        directoryPrefix = self._webpage_dir
        if not os.path.exists(directoryPrefix):
            os.makedirs(directoryPrefix)
            
        dirs = os.listdir(directoryPrefix)

        print(f"Cloning webpages to {directoryPrefix} \n")
        
        for webpage in webpages:
            if not webpage in dirs:
                os.system(f"wget --tries=2 --convert-links --adjust-extension --user-agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0' --no-parent -P {directoryPrefix}/{webpage} {webpage}")


        dirs = os.listdir(directoryPrefix)
        links = ""

        for dir in dirs:
            link = link_template.format(link=f"{dir}/index.html", title=dir)
            links += link

        index = index_template.format(links=links)

        with open(directoryPrefix+"/index.html", 'w') as f:
            f.write(index)      

    def _prepareWEB(self):
        """
        @brief Prepare the web server
        """

        nginx_conf = """\
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;
events {
        worker_connections 768;  
}
http {
        sendfile on;
        tcp_nopush on;
        tcp_nodelay on;
        keepalive_timeout 65;
        types_hash_max_size 2048;
        include /etc/nginx/mime.types;
        default_type application/octet-stream;
        ssl_protocols TLSv1 TLSv1.1 TLSv1.2 TLSv1.3; 
        ssl_prefer_server_ciphers on;
        access_log /var/log/traffic_gen/ACCESS_LOG;
        error_log /var/log/traffic_gen/ERROR_LOG;
        gzip on;
        include /etc/nginx/conf.d/*.conf;
        include /etc/nginx/sites-enabled/*;
}
"""

        base: ScionBase = self._emu.getLayer("Base")

        if(not self._custom_webpages):
            self._custom_webpages = base_dir+"/webpages.txt"

        if not os.path.exists(self._custom_webpages):
            raise ("webpages.txt not found please provide a file with a list of webpages to clone.")
        
        with open(self._custom_webpages, "r") as f:
            webpages = f.readlines()
            webpages = [webpage.strip() for webpage in webpages]

        self._cloneWebPages(webpages)
        web_patterns = [pattern for pattern in self._traffic_pattern["traffic_patterns"] if pattern["mode"] == TrafficMode.web.value]

        if not web_patterns:
            return
        
        server_asns = [pattern["destination"].split("-")[1] for pattern in web_patterns]
        client_asns = [pattern["source"].split("-")[1] for pattern in web_patterns]

        for asn in server_asns:
            as_ = base.getAutonomousSystem(int(asn))
            net_name = "net0"
            host = as_.getHost("traffic_gen")
            host.addSoftware("nginx-light")
            host.addSoftware("wget")
            host.addSharedFolder("/var/www/html", self._webpage_dir)
            host.setFile("/etc/nginx/nginx.conf", nginx_conf)

        for asn in client_asns:
            as_ = base.getAutonomousSystem(int(asn))
            net_name = "net0"
            host = as_.getHost("traffic_gen")
            host.addSharedFolder("/app", base_dir+"/web_client")
            host.addSoftware("wget")
            host.addSoftware("curl")
            host.addBuildCommand("pip install bs4 requests argparse")

    def prepare(self, dump_file: str) -> None:
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
            self._occupied_ports[asn] = 50001 # start from 50002 and increment by 1 for each new server


        
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
            log_folder = self._createLogFolder(asn)
            generator_host.addSharedFolder("/var/log/traffic_gen/", log_folder)
    
        self._prepareWEB()
        
        self._prepareSIGs()
        
        # check if BGP should be added
        modes = [pattern["mode"] for pattern in self._traffic_pattern["traffic_patterns"]]
        if not ("iperf" in modes or "web" in modes):
            print("Disabling BGP as no ipv4 applications in pattern")
            self._enable_bgp = False

        # add bgp
        if self._enable_bgp:
            self._addBGP()        

        print("\n\n\n")

    def _setUpBWTester(self, pattern: Dict[str, Union[str, Dict]], pattern_id: int) -> tuple[BWTestServer, BWTestClient]:
        """
        @brief Set up the BWTester
        """
        
        dest_asn = int(pattern["destination"].split("-")[1])

        port = self._occupied_ports[dest_asn]+2
        self._occupied_ports[dest_asn] = port

        btserver = BWTestServer(dest_asn, port, log_file=f"bwtestserver_{str(pattern_id)}.log")
     

        source_asn = int(pattern["source"].split("-")[1])
        dst_isd = int(pattern["destination"].split("-")[0])

        btclient = BWTestClient(source_asn, dst_isd, dest_asn, port, log_file=f"bwtestclient_{str(pattern_id)}.log")
        
        if "specialized_parameters" in pattern:
            for param in pattern["specialized_parameters"]:
                btclient.appendArgs(param, pattern["specialized_parameters"][param])
        elif "parameters" in pattern:
            # assemble cs string
            cs_str = ""
            cs_str += f"{pattern['parameters']['duration']}," if "duration" in pattern["parameters"] else "?,"
            cs_str += f"{pattern['parameters']['packet_size']}," if "packet_size" in pattern["parameters"] else "?,"
            cs_str += "?,"
            cs_str += f"{pattern['parameters']['bandwidth']}" if "bandwidth" in pattern["parameters"] else "?"
            btclient.setCS(cs_str)

        
        return btserver, btclient

    def _setUpIPerf(self, pattern: Dict[str, Union[str, Dict]], pattern_id: int) -> tuple[IPerfServer, IPerfClient]:
        """
        @brief Set up the IPerf
        """
        
        dest_asn = int(pattern["destination"].split("-")[1])

        port = self._occupied_ports[dest_asn]+2
        self._occupied_ports[dest_asn] = port

        ipserver = IPerfServer(dest_asn, port, log_file=f"IperfServer_{str(pattern_id)}.log")
     

        source_asn = int(pattern["source"].split("-")[1])
        dst_isd = int(pattern["destination"].split("-")[0])

        ipclient = IPerfClient(source_asn, dst_isd, dest_asn, port, log_file=f"IperfClient_{str(pattern_id)}.log")
        
        if "dst_ip" in pattern:
            ipclient.setDstIP(pattern["dst_ip"])

        if "specialized_parameters" in pattern:
            for param in pattern["specialized_parameters"]:
                ipclient.appendArgs(param, pattern["specialized_parameters"][param])
        elif "parameters" in pattern:
            if "bandwidth" in pattern["parameters"]:
                ipclient.setBandwidth(pattern["parameters"]["bandwidth"])
            if "packet_size" in pattern["parameters"]:
                ipclient.setPacketSize(pattern["parameters"]["packet_size"])
            if "duration" in pattern["parameters"]:
                ipclient.setDuration(pattern["parameters"]["duration"])
            
        return ipserver, ipclient
    
    def _setUpWeb(self, pattern: Dict[str, Union[str, Dict]], pattern_id: int) -> tuple[WebServer, WebClient]:
        """
        @brief Set up the Web
        """

        dest_asn = int(pattern["destination"].split("-")[1])


        webserver = WebServer(dest_asn, log_file=f"webserver_{str(pattern_id)}.log")
     

        source_asn = int(pattern["source"].split("-")[1])
        dst_isd = int(pattern["destination"].split("-")[0])


        webclient = WebClient(source_asn, dst_isd, dest_asn, log_file=f"webclient_{str(pattern_id)}.log")

        if "dst_ip" in pattern:
            webclient.setDstIP(pattern["dst_ip"])

        if "specialized_parameters" in pattern:
            for param in pattern["specialized_parameters"]:
                webclient.appendArgs(param, pattern["specialized_parameters"][param])
        elif "parameters" in pattern:
            if "duration" in pattern["parameters"]:
                webclient.setDuration(pattern["parameters"]["duration"])
    
        return webserver, webclient
        
    def _generate_patterns(self):

        print("Starting Traffic Generation")
        old_offset = 0
        pattern_id = 0
        
        # iterate through patterns which are ordered by start_offset
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

            elif pattern["mode"] == TrafficMode.web.value:
                print(f"generating WEB traffic from AS{pattern['source']} to AS{pattern['destination']}")

                webserver, webclient = self._setUpWeb(pattern, pattern_id)

                webserver.start()
                webclient.start()

            else:
                raise Exception(f"Invalid mode {pattern['mode']}")

            pattern_id += 1

        print("Traffic Generation Completed\n\n")

    def build(self) -> None:
        """
        @brief Build the traffic generator
        """

        output_dir = self._seedCompileDir

        self._emu.render()
        self._emu.compile(Docker(internetMapEnabled=True), output_dir, override=True)
            
        docker = DockerClient(compose_files=[output_dir+"/docker-compose.yml"])

        docker.compose.build()

    def run(self) -> None:
        """
        @brief Run the traffic generator
        """
        
        output_dir = self._seedCompileDir

        self._parsePattern()
        
        docker = DockerClient(compose_files=[output_dir+"/docker-compose.yml"])

       
        docker.compose.up(detach=True)  

        
        print(f"\n\n\nWaiting {self._wait_for_up} seconds for Containers to be ready\n\n\n")
        time.sleep(self._wait_for_up)   

        self._generate_patterns()

    def stop(self) -> None:
        """
        @brief Stop the traffic generator
        """

        outtput_dir = self._seedCompileDir

        zipped_logs_path = self.zip_logs()
        print(f"Logs zipped to {zipped_logs_path}")
        docker = DockerClient(compose_files=[outtput_dir+"/docker-compose.yml"])
        docker.compose.down()

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Traffic Generator")
    parser.add_argument("-p","--pattern_file", help="The pattern file")
    parser.add_argument("-w", "--wait_for_up", help="The time to wait for containers to be ready", default=15, type=int)
    parser.add_argument("-s", "--seed_file", help="The seed bin file to use for emulation. You can obtain this by using emu.dump() before rendering a seed emulation")
    parser.add_argument("-b", "--skip_build", help="skip the Build process. This can be helpful if you want to run several generations back to back. Note that some changes such as adding sig option to patterns require rebuilding", action="store_true")
    parser.add_argument("-l", "--logdir", help="The directory to store logs", type=str)
    parser.add_argument("-m", "--traffic_matrix", help="The traffic matrix file", type=str)
    parser.add_argument("-ts", "--time_step", help="The time step for the traffic matrix", type=str)
    parser.add_argument("-c", "--seed_compiled_dir", help="The directory to store the compiled seed emulation", type=str)
    parser.add_argument("-cw", "--custom_webpages", help="The file containing a list of webpages to clone", type=str)
    parser.add_argument("-wd", "--webpage_dir", help="The directory to clone the webpages to", type=str)

    args = parser.parse_args()


    if not args.pattern_file:
        if not args.traffic_matrix:
            print(f"no pattern file provided. Do you want to use {base_dir+'/pattern_sample.json'}? [Y/n]")
            response = input()
            if response.lower() == "n":
                exit(0)
            else:
                args.pattern_file = base_dir+"/pattern_sample.json"
        else:
            if not args.time_step:
                print("no time step provided. Do you want to use 10s? [Y/n]")
                response = input()
                if response.lower() == "n":
                    exit(0)
                else:
                    args.time_step = "10s"
            tm = TrafficMatrix()
            tm.fromFile(args.traffic_matrix).setTimeStep(args.time_step).export(base_dir+"/pattern_matrix.json")
            args.pattern_file = base_dir+"/pattern_matrix.json"



    if not args.seed_file:
        print(f"no seed file provided. Do you want to use {base_dir+'/seed.bin'}? [Y/n]")
        response = input()
        if response.lower() == "n":
            exit(0)
        else:
            args.seed_file = base_dir+"/seed.bin"

    if not args.logdir:
        print(f"no logdir provided. Do you want to use {base_dir+'/logs'}? [Y/n]")
        response = input()
        if response.lower() == "n":
            exit(0)
        else:
            args.logdir = base_dir+"/logs"

    
    if not args.seed_compiled_dir:
        print(f"no seed compiled dir provided. Do you want to use {base_dir+'/seed-compiled'}? [Y/n]")
        response = input()
        if response.lower() == "n":
            exit(0)
        else:
            args.seed_compiled_dir = base_dir+"/seed-compiled"


    tg = TrafficGenerator(args.pattern_file, args.wait_for_up, args.logdir, args.seed_compiled_dir)

    if args.custom_webpages:
        tg.setCustomWebPages(args.custom_webpages)
    if args.webpage_dir:
        tg.setWebpageDir(args.webpage_dir)

    # handle ctrl+c
    signal.signal(signal.SIGINT, partial(handler, tg))
    # pass seed topology
    tg.prepare(args.seed_file) 
    
    if not args.skip_build:
        tg.build()
    
    tg.run()

    print("press CTRL+C to stop emulation\n\n\n")
    
    signal.pause()