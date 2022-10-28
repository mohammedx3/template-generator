#!/usr/bin/python3
from re import template
import ipaddr
import sys
import os
import argparse
import configparser
from troposphere.ec2 import (
    VPC,
    Route,
    EIP,
    InternetGateway,
    RouteTable,
    Subnet,
    SubnetRouteTableAssociation,
    VPCGatewayAttachment,
    NatGateway
)
from troposphere import Ref, Region, Tags, Template, GetAtt, Parameter, Output
from netaddr import IPNetwork, cidr_merge, cidr_exclude

class IPSplitter(object):
    def __init__(self, base_range):
        self.avail_ranges = set((IPNetwork(base_range),))

    def get_subnet(self, prefix, count=None):
        for ip_network in self.get_available_ranges():
            subnets = list(ip_network.subnet(prefix, count=count))
            if not subnets:
                continue
            self.remove_avail_range(ip_network)
            self.avail_ranges = self.avail_ranges.union(set(cidr_exclude(ip_network, cidr_merge(subnets)[0])))
            return subnets

    def get_available_ranges(self):
        return sorted(self.avail_ranges, key=lambda x: x.prefixlen, reverse=True)

    def remove_avail_range(self, ip_network):
        self.avail_ranges.remove(ip_network)


class Env:
    def __init__(self, name, region, vpc_ip, net_mask, dns_support, dns_hostnames, instance_tenancy):
        self.name = name
        self.region = region
        self.vpc_ip = vpc_ip
        self.net_mask = net_mask
        self.dns_support = dns_support
        self.dns_hostnames = dns_hostnames
        self.instance_tenancy = instance_tenancy

    def create_resources(self):
        t = Template()
        t.set_version("2010-09-09")
        t.set_description("AWS CloudFormation VPC with multi-azs subnets.")
        tags=Tags(
                    Environment=self.name,
                    Region=self.region
                )
        s = IPSplitter(f"{self.vpc_ip}/{self.net_mask}")
        subnets = s.get_subnet(self.net_mask+2, count=3)
        
        # Parameters
        az_a = t.add_parameter(
            Parameter(
                "AvailabilityZoneA",
                Default=f"{self.region}a",
                Description="The AvailabilityZone in which the subnet will be created.",
                Type="String",
            )
        )

        az_b = t.add_parameter(
            Parameter(
                "AvailabilityZoneB",
                Default=f"{self.region}b",
                Description="The AvailabilityZone in which the subnet will be created.",
                Type="String",
            )
        )

        az_c = t.add_parameter(
            Parameter(
                "AvailabilityZoneC",
                Default=f"{self.region}c",
                Description="The AvailabilityZone in which the subnet will be created.",
                Type="String",
            )
        )

        vpc_cidr = t.add_parameter(
            Parameter(
                "VPCCIDR",
                Default=f"{self.vpc_ip}/{self.net_mask}",
                Description="The IP address space for this VPC, in CIDR notation",
                Type="String",
            )
        )

        private_subnet = t.add_parameter(
            Parameter(
                "PrivateSubnetCIDR",
                Default=str(subnets[0]),
                Description="Private subnet network with no access to internet.",
                Type="String",
            )
        )

        public_subnet = t.add_parameter(
            Parameter(
                "PublicSubnetCIDR",
                Default=str(subnets[1]),
                Description="Public subnet network with open access to internet.",
                Type="String",
            )
        )

        protected_subnet = t.add_parameter(
            Parameter(
                "ProtectedSubnetCIDR",
                Default=str(subnets[2]),
                Description="Protected subnet network with access to internet through NAT..",
                Type="String",
            )
        )


        # Resources
        vpc = t.add_resource(
            # VPC("VPC", CidrBlock=f"{self.vpc_ip}/{self.net_mask}", 
            VPC("VPC", CidrBlock=Ref(vpc_cidr), 
            EnableDnsSupport=self.dns_support,
            EnableDnsHostnames=self.dns_hostnames,
            Tags=tags
            ),

        )

        private_subnet = t.add_resource(
            Subnet(
                "PrivateSubnet",
                CidrBlock=Ref(private_subnet),
                AvailabilityZone=Ref(az_c),
                VpcId=Ref(vpc),
                Tags=tags
            )
        )

        public_subnet = t.add_resource(
            Subnet(
                "PublicSubnet",
                CidrBlock=Ref(public_subnet),
                AvailabilityZone=Ref(az_b),
                VpcId=Ref(vpc),
                Tags=tags
            )
        )

        protected_subnet = t.add_resource(
            Subnet(
                "ProtectedSubnet",
                CidrBlock=Ref(protected_subnet),
                AvailabilityZone=Ref(az_c),
                VpcId=Ref(vpc),
                Tags=tags
            )
        )

        internet_gateway = t.add_resource(
            InternetGateway(
                "InternetGateway",
                Tags=tags
            )
        )

        net_gw_vpc_attachment = t.add_resource(
            VPCGatewayAttachment(
                "NatAttachment",
                VpcId=Ref(vpc),
                InternetGatewayId=Ref(internet_gateway),
            )
        )

        protected_route_table = t.add_resource(
            RouteTable(
                "ProtectedRouteTable",
                VpcId=Ref(vpc),
                Tags=tags
            )
        )

        public_route_table = t.add_resource(
            RouteTable(
                "PublicRouteTable",
                VpcId=Ref(vpc),
                Tags=tags
            )
        )

        public_route_association = t.add_resource(
            SubnetRouteTableAssociation(
                "PublicRouteAssociation",
                SubnetId=Ref(public_subnet),
                RouteTableId=Ref(public_route_table),
            )
        )

        default_public_route = t.add_resource(
            Route(
                "PublicDefaultRoute",
                RouteTableId=Ref(public_route_table),
                DestinationCidrBlock="0.0.0.0/0",
                GatewayId=Ref(internet_gateway),
            )
        )

        protected_route_association = t.add_resource(
            SubnetRouteTableAssociation(
                "ProtectedRouteAssociation",
                SubnetId=Ref(protected_subnet),
                RouteTableId=Ref(protected_route_table),
            )
        )

        nat_eip = t.add_resource(
            EIP(
                "NatEip",
                Domain="vpc",
                Tags=tags
            )
        )

        nat = t.add_resource(
            NatGateway(
                "Nat",
                AllocationId=GetAtt(nat_eip, "AllocationId"),
                SubnetId=Ref(public_subnet),
                Tags=tags
            )
        )

        nat_route = t.add_resource(
            Route(
                "NatRoute",
                RouteTableId=Ref(protected_route_table),
                DestinationCidrBlock="0.0.0.0/0",
                NatGatewayId=Ref(nat),
            )
        )

        # Outputs
        nat_eip=t.add_output(
            Output(
                "NatEip",
                Value=Ref(nat_eip),
                Description="Nat Elastic IP.",
            )
        )

        private_subnet = t.add_output(
            Output(
                "PrivateSubnetId",
                Description="SubnetId of the private subnet.",
                Value=Ref(private_subnet),
            )
        )

        public_subnet = t.add_output(
            Output(
                "PublicSubnetId",
                Description="SubnetId of the public subnet.",
                Value=Ref(public_subnet),
            )
        )

        protected_subnet = t.add_output(
            Output(
                "ProtectedSubnetId",
                Description="SubnetId of the protected subnet.",
                Value=Ref(protected_subnet),
            )
        )

        VPCId = t.add_output(
            Output(
                "VPCId",
                Description="VPCId of the newly created VPC",
                Value=Ref(vpc),
            )
        )

        nat = t.add_output(
            Output(
                "NatGatewayId",
                Description="Id of the internet gatway.",
                Value=Ref(nat),
            )
        )

        public_route_table = t.add_output(
            Output(
                "PublicRouteTableId",
                Description="Id of the public route table.",
                Value=Ref(public_route_table),
            )
        )

        protected_route_table = t.add_output(
            Output(
                "ProtectedRouteTableId",
                Description="Id of the protected route table.",
                Value=Ref(protected_route_table),
            )
        )
        
        internet_gateway = t.add_output(
            Output(
                "InternetGatewayId",
                Description="Id of the internet gateway..",
                Value=Ref(internet_gateway),
            )
        )

        return t.to_json()

    def display(self):
        return 'Env name: ' + self.name + '\nVPC IP: '+ self.vpc_ip + '\nNet mask: '+ self.net_mask+ '\nDNS support: ' + self.dns_support + '\nDNS hostnames: ' + self.dns_hostnames + '\nInstance tenancy: ' + self.instance_tenancy

class InvalidTemplate(Exception):
    def __init__(self, reason, message="Template is not valid:"):
        self.reason = reason
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"{self.message} {self.reason}"

def main():
    if os.path.exists('values.txt') and os.environ["AWS_REGION"]:
        args = configparser.ConfigParser()
        args.read(sys.argv[1:])
        for each_section in args.sections():
            env = each_section
            region = os.environ["AWS_REGION"]
            vpc_ip = args[env]['vpc_ip']
            net_mask = int(args[env]['net_mask'])
            dns_support = args[env]['dns_support']
            dns_hostnames = args[env]['dns_hostnames']
            instance_tenancy = args[env]['instance_tenancy']

            env=Env(env, region, vpc_ip, net_mask, dns_support, dns_hostnames, instance_tenancy)
            # with open(f"{env.name}.json", "a") as f:
            #     print(env.create_resources(), file=f)
            print(env.create_resources()) 

    else:
        raise InvalidTemplate(f"You must have a values.txt file with values within it and specifiy AWS_REGION as environment variable to run the script.")


if __name__ == '__main__':
    main()
