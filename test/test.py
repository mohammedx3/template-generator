# from taskcat.testing import CFNTest
import boto3
import os
from pathlib import Path
from cloud_radar.cf.e2e import Stack
import pytest
import sys
# import unittest

filepath = "./dev.json"
template_path = Path(filepath)
region = os.environ["AWS_REGION"]
regions = [region]
vpc_cidr = '10.0.0.0/24'
private_subnet = '10.0.0.0/26'
public_subnet = '10.0.0.64/26'
protected_subnet = '10.0.0.128/26'

params = {
    "VPCCIDR": vpc_cidr, "PrivateSubnetCIDR": private_subnet, "PublicSubnetCIDR": public_subnet, "ProtectedSubnetCIDR": protected_subnet
}

# class InvalidTest(Exception):
#     def __init__(self, reason, message="Template is not valid:"):
#         self.reason = reason
#         self.message = message
#         super().__init__(self.message)

#     def __str__(self):
#         return f"{self.message} {self.reason}"
def find_output(output_key, stacks):
    for stack in stacks:
        for output in stack.outputs:
            if output.key == output_key:
                return output.value
@pytest.fixture
def test_internet_gateway(client, internet_gateway_id):
    # try:
        internet_gateway = client.describe_internet_gateways(InternetGatewayIds=[internet_gateway_id])
        for i in internet_gateway['InternetGateways']:
            for index in i['Attachments']:
                assert index['State']
    # except:
    #     raise InvalidTest(f"Internet gateway is not attached or it does not exist.")
@pytest.fixture
def test_protected_route_table(client, protected_route_table_id, vpc_cidr, nat_gateway_id):
    # try:
    route_table = client.describe_route_tables(RouteTableIds=[protected_route_table_id])
    for i in route_table['RouteTables']:
        # try:
        assert i['Routes'][0]['DestinationCidrBlock'] == vpc_cidr and i['Routes'][0]['GatewayId'] == "local"
        assert i['Routes'][1]['DestinationCidrBlock'] == "0.0.0.0/0" and i['Routes'][1]['NatGatewayId'] == nat_gateway_id
    #         except:
    #             raise InvalidTest(f"Route tables were not created correctly.")
    # except:
    #     raise InvalidTest(f"Invalid protected route table.")
@pytest.fixture
def test_public_route_table(client, public_route_table_id, vpc_cidr, internet_gateway_id):
    # try:
    route_table = client.describe_route_tables(RouteTableIds=[public_route_table_id])
    for i in route_table['RouteTables']:
        assert i['Routes'][0]['DestinationCidrBlock'] == vpc_cidr and i['Routes'][0]['GatewayId'] == "local"
        assert i['Routes'][1]['DestinationCidrBlock'] == "0.0.0.0/0" and i['Routes'][1]['GatewayId'] == internet_gateway_id
    # except:
    #     raise InvalidTest(f"Invalid public route table.")
@pytest.fixture
def test_nat_gateway(client, nat_gateway_id):
    # try:
        nat_gateway = client.describe_nat_gateways(NatGatewayIds=[nat_gateway_id])
        for i in nat_gateway['InternetGateways']:
            for index in i['Attachments']:
                assert index['State']
    # except:
    #     raise InvalidTest(f"Internet gateway is not attached or it does not exist.")
@pytest.fixture
def test_nat(client, nat_gateway_id, nat_eip):
    # try:
    nat = client.describe_nat_gateways(NatGatewayIds=[nat_gateway_id])
    for i in nat['NatGateways']:
        for j in i['NatGatewayAddresses']:
            assert j['PublicIp'] == nat_eip and i['NatGatewayId'] == nat_gateway_id
                    # print('Nat gateway was created successfully.')
    # except:
    #     raise InvalidTest(f"Nat IP is not a a valid ip or it does not exist.")
@pytest.fixture
def test_vpc(client, vpc_id):
    # try:
    vpc = client.describe_vpcs(VpcIds=[vpc_id])
    for i in vpc['Vpcs']:
        return i
        # vpc_cidr = i['CidrBlock']
        # vpc_instance_tenancy = i['InstanceTenancy']
        # assert vpc_cidr in vpc_cidr
        # assert "default" in vpc_instance_tenancy
        return vpc_cidr
    # except:
    #     raise InvalidTest(f"VPC CIDR or instane tenancy is not set correctly.")

@pytest.fixture
def test_subnets(client, private_subnet, public_subnet, protected_subnet, private_subnet_id, public_subnet_id, protected_subnet_id):
    private_subnet_id = client.describe_subnets(SubnetIds=[private_subnet_id])
    public_subnet_id = client.describe_subnets(SubnetIds=[public_subnet_id])
    protected_subnet_id = client.describe_subnets(SubnetIds=[protected_subnet_id])

    for i in private_subnet_id['Subnets']:
        subnet_cidr = i['CidrBlock']
        assert private_subnet in subnet_cidr

    for i in public_subnet_id['Subnets']:
        subnet_cidr = i['CidrBlock']
        assert public_subnet in subnet_cidr

    for i in protected_subnet_id['Subnets']:
        subnet_cidr = i['CidrBlock']
        assert protected_subnet in subnet_cidr

# pytest_plugins = [
#     'plugins.start_plugin',
# ]


# def pytest_sessionstart(session):
#   print("before")

def test_main():
    client = boto3.client('ec2', region_name=region)
    with Stack(template_path, params, regions) as stacks:
        nat_gateway_id = find_output("NatGatewayId", stacks)
        nat_eip = find_output("NatEip", stacks)
        internet_gateway_id = find_output("InternetGatewayId", stacks)
        private_subnet_id = find_output("PrivateSubnetId", stacks)
        public_subnet_id = find_output("PublicSubnetId", stacks)
        protected_subnet_id = find_output("ProtectedSubnetId", stacks)
        public_route_table_id = find_output("PublicRouteTableId", stacks)
        protected_route_table_id = find_output("ProtectedRouteTableId", stacks)
        vpc_id = find_output("VPCId", stacks)

        # print(f"Testing Nat IP...")
        # test_nat(client, nat_gateway_id, nat_eip)
        print(f"Testing VPC...")
        i = test_vpc(client, vpc_id)
        print(i)
        vpc_cidr_result=i['CidrBlock']
        vpc_instance_tenancy_result=i['InstanceTenancy']
        print(vpc_cidr)
        print(vpc_cidr_result)
        print(vpc_instance_tenancy_result)
        assert vpc_cidr in vpc_cidr_result
        assert "default" in vpc_instance_tenancy_result
        # print(f"Testing subnets...")
        # test_subnets(client, private_subnet, public_subnet, protected_subnet, private_subnet_id, public_subnet_id, protected_subnet_id)
        # print(f"Testing internet gateway...")
        # test_internet_gateway(client, internet_gateway_id)
        # print(f"Testing public route table...")
        # test_public_route_table(client, public_route_table_id, vpc_cidr, internet_gateway_id)
        # print(f"Testing protected route table...")
        # test_protected_route_table(client, protected_route_table_id, vpc_cidr, nat_gateway_id)

if __name__ == '__main__':
    test_main()

