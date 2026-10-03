"""Partition behavior allows temporary duplicate work, but never global repair."""
from tests.resilience.test_agents import agent
from src.resilience.transport import Packet


def test_disconnected_agents_do_not_share_claims():
    a,_,_=agent();b,_,_=agent();b.uav.id=1
    a.claims[1]={'owner':0,'bid':5,'until':10}
    b.claims[1]={'owner':1,'bid':8,'until':10}
    assert a.claims[1]['owner']==0
    assert b.claims[1]['owner']==1
    a.receive(Packet(1,-2,'beacon',{'claims':list(b.claims.items())},0),1)
    assert a.claims[1]['owner']==1
    b.receive(Packet(0,-2,'beacon',{'claims':list(a.claims.items())},0),1)
    assert b.claims[1]['owner']==1
