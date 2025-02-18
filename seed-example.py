

from seedemu.compiler import Docker
from seedemu.core import Emulator
from seedemu.layers import ScionBase, ScionRouting, ScionIsd, Scion, Ospf
from seedemu.layers.Scion import LinkType as ScLinkType

# Initialize
emu = Emulator()
base = ScionBase()
routing = ScionRouting()
scion_isd = ScionIsd()
scion = Scion()
ospf = Ospf()

# Create ISDs
base.createIsolationDomain(1)


# Ases 

# AS-110
as110 = base.createAutonomousSystem(110)
scion_isd.addIsdAs(1,110,is_core=True)
as110.createNetwork('net0').setDefaultLinkProperties(latency=0,bandwidth=0,packetDrop=0).setMtu(1400)
as110.createControlService('cs_1').joinNetwork('net0')
as_110_br1 = as110.createRouter('br1').joinNetwork('net0')
as_110_br1.crossConnect(111,'br1','10.3.0.2/29',latency=0,bandwidth=0,packetDrop=0,MTU=1280)
as_110_br2 = as110.createRouter('br2').joinNetwork('net0')
as_110_br2.crossConnect(112,'br1','10.3.0.10/29',latency=0,bandwidth=0,packetDrop=0,MTU=1280)

# AS-111
as111 = base.createAutonomousSystem(111)
scion_isd.addIsdAs(1,111,is_core=False)
scion_isd.setCertIssuer((1,111),issuer=110)
as111.createNetwork('net0').setDefaultLinkProperties(latency=0, bandwidth=0, packetDrop=0)
as111.createControlService('cs_1').joinNetwork('net0')
as_111_br1 = as111.createRouter('br1').joinNetwork('net0')
as_111_br1.crossConnect(110,'br1','10.3.0.3/29',latency=0,bandwidth=0,packetDrop=0,MTU=1280)

# AS-112
as112 = base.createAutonomousSystem(112)
scion_isd.addIsdAs(1,112,is_core=False)
scion_isd.setCertIssuer((1,112),issuer=110)
as112.createNetwork('net0').setDefaultLinkProperties(latency=0, bandwidth=0, packetDrop=0)
as112.createControlService('cs_1').joinNetwork('net0')
as_112_br1 = as112.createRouter('br1').joinNetwork('net0')
as_112_br1.crossConnect(110,'br2','10.3.0.11/29',latency=0,bandwidth=0,packetDrop=0,MTU=1280)


# Inter-AS routing
scion.addXcLink((1,110),(1,111),ScLinkType.Transit,a_router='br1',b_router='br1')
scion.addXcLink((1,110),(1,112),ScLinkType.Transit,a_router='br2',b_router='br1')


# Rendering
emu.addLayer(base)
emu.addLayer(routing)
emu.addLayer(scion_isd)
emu.addLayer(scion)
emu.addLayer(ospf)

emu.dump("./seed.bin")

# emu.render()

# # Compilation
# emu.compile(Docker(internetMapEnabled=True), './seed-compiled')
