#!/usr/local/bin/python3
import sys
import os
import argparse
import yaml
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
from troposphere import Ref, Tags, Template, GetAtt, Parameter, Output
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
    def __init__(self, name, availablility_zones, region, vpc_ip, net_mask, dns_support, dns_hostnames, instance_tenancy):
        self.name = name
        self.region = region
        self.vpc_ip = vpc_ip
        self.net_mask = net_mask
        self.dns_support = dns_support
        self.dns_hostnames = dns_hostnames
        self.instance_tenancy = instance_tenancy
        self.availablility_zones = availablility_zones

    def create_template(self):
        template = Template()
        template.set_version("2010-09-09")
        template.set_description("AWS CloudFormation VPC with multi-azs subnets.")
        subnets = IPSplitter(f"{self.vpc_ip}/{self.net_mask}")
        subnets = subnets.get_subnet(self.net_mask+2, count=3)
        tags = Tags(
                    Environment=self.name,
                    Region=self.region
                )

        # Parameters
        availability_zone_a = template.add_parameter(
            Parameter(
                "AvailabilityZoneA",
                Default=self.availablility_zones[0],
                Description="The AvailabilityZone in which the subnet will be created.",
                Type="String",
            )
        )

        availability_zone_b = template.add_parameter(
            Parameter(
                "AvailabilityZoneB",
                Default=self.availablility_zones[1],
                Description="The AvailabilityZone in which the subnet will be created.",
                Type="String",
            )
        )

        availability_zone_c = template.add_parameter(
            Parameter(
                "AvailabilityZoneC",
                Default=self.availablility_zones[2],
                Description="The AvailabilityZone in which the subnet will be created.",
                Type="String",
            )
        )

        vpc_cidr = template.add_parameter(
            Parameter(
                "VPCCIDR",
                Default=f"{self.vpc_ip}/{self.net_mask}",
                Description="The IP address space for this VPC, in CIDR notation",
                Type="String",
            )
        )

        private_subnet = template.add_parameter(
            Parameter(
                "PrivateSubnetCIDR",
                Default=str(subnets[0]),
                Description="Private subnet network with no access to internet.",
                Type="String",
            )
        )

        public_subnet = template.add_parameter(
            Parameter(
                "PublicSubnetCIDR",
                Default=str(subnets[1]),
                Description="Public subnet network with open access to internet.",
                Type="String",
            )
        )

        protected_subnet = template.add_parameter(
            Parameter(
                "ProtectedSubnetCIDR",
                Default=str(subnets[2]),
                Description="Protected subnet network with access to internet through NAT.",
                Type="String",
            )
        )

        # Resources
        vpc = template.add_resource(
            VPC(
                "VPC", CidrBlock=Ref(vpc_cidr),
                EnableDnsSupport=self.dns_support,
                EnableDnsHostnames=self.dns_hostnames,
                Tags=tags
            )
        )

        private_subnet = template.add_resource(
            Subnet(
                "PrivateSubnet",
                CidrBlock=Ref(private_subnet),
                AvailabilityZone=Ref(availability_zone_a),
                VpcId=Ref(vpc),
                Tags=tags
            )
        )

        public_subnet = template.add_resource(
            Subnet(
                "PublicSubnet",
                CidrBlock=Ref(public_subnet),
                AvailabilityZone=Ref(availability_zone_b),
                VpcId=Ref(vpc),
                Tags=tags
            )
        )

        protected_subnet = template.add_resource(
            Subnet(
                "ProtectedSubnet",
                CidrBlock=Ref(protected_subnet),
                AvailabilityZone=Ref(availability_zone_c),
                VpcId=Ref(vpc),
                Tags=tags
            )
        )

        internet_gateway = template.add_resource(
            InternetGateway(
                "InternetGateway",
                Tags=tags
            )
        )

        net_gw_vpc_attachment = template.add_resource(
            VPCGatewayAttachment(
                "NatAttachment",
                VpcId=Ref(vpc),
                InternetGatewayId=Ref(internet_gateway),
            )
        )

        protected_route_table = template.add_resource(
            RouteTable(
                "ProtectedRouteTable",
                VpcId=Ref(vpc),
                Tags=tags
            )
        )

        public_route_table = template.add_resource(
            RouteTable(
                "PublicRouteTable",
                VpcId=Ref(vpc),
                Tags=tags
            )
        )

        public_route_association = template.add_resource(
            SubnetRouteTableAssociation(
                "PublicRouteAssociation",
                SubnetId=Ref(public_subnet),
                RouteTableId=Ref(public_route_table),
            )
        )

        default_public_route = template.add_resource(
            Route(
                "PublicDefaultRoute",
                RouteTableId=Ref(public_route_table),
                DestinationCidrBlock="0.0.0.0/0",
                GatewayId=Ref(internet_gateway),
            )
        )

        protected_route_association = template.add_resource(
            SubnetRouteTableAssociation(
                "ProtectedRouteAssociation",
                SubnetId=Ref(protected_subnet),
                RouteTableId=Ref(protected_route_table),
            )
        )

        nat_eip = template.add_resource(
            EIP(
                "NatEip",
                Domain="vpc",
                Tags=tags
            )
        )

        nat_gateway = template.add_resource(
            NatGateway(
                "Nat",
                AllocationId=GetAtt(nat_eip, "AllocationId"),
                SubnetId=Ref(public_subnet),
                Tags=tags
            )
        )

        nat_route = template.add_resource(
            Route(
                "NatRoute",
                RouteTableId=Ref(protected_route_table),
                DestinationCidrBlock="0.0.0.0/0",
                NatGatewayId=Ref(nat_gateway),
            )
        )

        # Outputs
        nat_eip = template.add_output(
            Output(
                "NatEip",
                Value=Ref(nat_eip),
                Description="Nat Elastic IP.",
            )
        )

        private_subnet = template.add_output(
            Output(
                "PrivateSubnetId",
                Description="SubnetId of the private subnet.",
                Value=Ref(private_subnet),
            )
        )

        public_subnet = template.add_output(
            Output(
                "PublicSubnetId",
                Description="SubnetId of the public subnet.",
                Value=Ref(public_subnet),
            )
        )

        protected_subnet = template.add_output(
            Output(
                "ProtectedSubnetId",
                Description="SubnetId of the protected subnet.",
                Value=Ref(protected_subnet),
            )
        )

        vpc_id = template.add_output(
            Output(
                "VPCId",
                Description="VPCId of the newly created VPC",
                Value=Ref(vpc),
            )
        )

        nat = template.add_output(
            Output(
                "NatGatewayId",
                Description="Id of the NAT gateway.",
                Value=Ref(nat_gateway),
            )
        )

        public_route_table = template.add_output(
            Output(
                "PublicRouteTableId",
                Description="Id of the public route table.",
                Value=Ref(public_route_table),
            )
        )

        protected_route_table = template.add_output(
            Output(
                "ProtectedRouteTableId",
                Description="Id of the protected route table.",
                Value=Ref(protected_route_table),
            )
        )

        internet_gateway = template.add_output(
            Output(
                "InternetGatewayId",
                Description="Id of the internet gateway..",
                Value=Ref(internet_gateway),
            )
        )
        return template.to_json()

    def display(self):
        return 'Env name: ' + self.name + 'Availability zones: ' + self.availablility_zones + '\nVPC IP: ' + self.vpc_ip + '\nNet mask: ' + self.net_mask + '\nDNS support: ' + self.dns_support + '\nDNS hostnames: ' + self.dns_hostnames + '\nInstance tenancy: ' + self.instance_tenancy


class InvalidTemplate(Exception):
    def __init__(self, reason, message="Template is not valid:"):
        self.reason = reason
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"{self.message} {self.reason}"

def parse_args(args):
    parser = argparse.ArgumentParser(description='Create AWS Cloudformation template for multi AZs VPC for different environments.')
    parser.add_argument('--input_path', required=False, default="./values.yaml", type=str, help='Path to input file with environment values, defaults to working directory..')
    parser.add_argument('--output_path', required=False, default="./", type=str, help='Path to the generated template, defaults to working directory.')
    return parser.parse_args(args)


def main():
    args = parse_args(sys.argv[1:])
    input_path = args.input_path
    output_path = args.output_path
    if os.path.exists(input_path):
        with open(input_path, 'r') as values:
            data = yaml.safe_load(values)
            for key, value in data.items():
                availablility_zones = []
                env = key
                region = data[key]['region']
                vpc_ip = data[key]['vpcIp']
                net_mask = int(data[key]['netMask'])
                dns_support = data[key]['dnsSupport']
                dns_hostnames = data[key]['dnsHostnames']
                instance_tenancy = data[key]['instanceTenancy']
                for i in data[key]['availabilityZones']:
                    availablility_zones.append(i)
                env = Env(env, availablility_zones, region, vpc_ip, net_mask, dns_support, dns_hostnames, instance_tenancy)
                with open(f"{output_path}/{env.name}.json", "w+") as template_file:
                    template_file.write(env.create_template())
                    template_file.seek(0)
                    template = template_file.read()
                    print(template)
    else:
        raise InvalidTemplate("Coud not find the values.yaml file, make sure it exists in the working directory or specify the path with --input_path.")


if __name__ == '__main__':
    main()
