import boto3
import atexit

REGION = "us-east-1"
VPC_CIDR = '10.0.0.0/24'
PRIVATE_SUBNET_CIDR = '10.0.0.0/26'
PUBLIC_SUBNET_CIDR = '10.0.0.64/26'
PROTECTED_SUBNET_CIDR = '10.0.0.128/26'
TEMPLATE_FILE_LOCATION = 'dev.json'
STACK_NAME = 'test-template-generator'

CLIENT = boto3.client('ec2', region_name=REGION)
CF_CLIENT = boto3.client("cloudformation", region_name="us-east-1")
CF_RESOURCE = boto3.resource("cloudformation", region_name="us-east-1")


def find_output(output_key, stack):
    for output in stack.outputs:
        key = output["OutputKey"]
        value = output["OutputValue"]
        if key == output_key:
            return value


def ids(stack):
    return {
        "nat_gateway_id": find_output("NatGatewayId", stack),
        "nat_eip": find_output("NatEip", stack),
        "internet_gateway_id": find_output("InternetGatewayId", stack),
        "private_subnet_id": find_output("PrivateSubnetId", stack),
        "public_subnet_id": find_output("PublicSubnetId", stack),
        "protected_subnet_id": find_output("ProtectedSubnetId", stack),
        "public_route_table_id": find_output("PublicRouteTableId", stack),
        "protected_route_table_id": find_output("ProtectedRouteTableId", stack),
        "vpc_id": find_output("VPCId", stack)
    }

try:
    with open(TEMPLATE_FILE_LOCATION, "r") as template_file:
        TEMPLATE_CONTENT = template_file.read()

    print("Creating {}".format(STACK_NAME))
    CF_CLIENT.create_stack(
        StackName=STACK_NAME,
        TemplateBody=TEMPLATE_CONTENT,
    )
    print("Waiting for stack creation to complete...")
    WAITER = CF_CLIENT.get_waiter('stack_create_complete').wait(StackName=STACK_NAME)
except:
    raise Exception("Stack was not created correctly.")

try:
    STACK = CF_RESOURCE.Stack(STACK_NAME)
    NAT_GATEWAY_ID = ids(STACK)["nat_gateway_id"]
    NAT_EIP = ids(STACK)["nat_eip"]
    INTERNET_GATEWAY_ID = ids(STACK)["internet_gateway_id"]
    PRIVATE_SUBNET_ID = ids(STACK)["private_subnet_id"]
    PUBLIC_SUBNET_ID = ids(STACK)["public_subnet_id"]
    PROTECTED_SUBNET_ID = ids(STACK)["protected_subnet_id"]
    PUBLIC_ROUTE_TABLE_ID = ids(STACK)["public_route_table_id"]
    PROTECTED_ROUTE_TABLE_ID = ids(STACK)["protected_route_table_id"]
    VPC_ID = ids(STACK)["vpc_id"]
except:
    raise Exception("Could not get all the required outputs.")


def test_nat_gateway():
    nat_gateway = CLIENT.describe_nat_gateways(NatGatewayIds=[NAT_GATEWAY_ID])
    assert len(nat_gateway['NatGateways']) == 1
    public_ip = nat_gateway['NatGateways'][0]['NatGatewayAddresses'][0]['PublicIp']
    assert public_ip == NAT_EIP


def test_internet_gateway():
    internet_gateway = CLIENT.describe_internet_gateways(InternetGatewayIds=[INTERNET_GATEWAY_ID])
    assert len(internet_gateway['InternetGateways']) == 1
    state = internet_gateway['InternetGateways'][0]['Attachments'][0]['State']
    assert state == 'available'


def test_protected_route_table():
    route_table = CLIENT.describe_route_tables(RouteTableIds=[PROTECTED_ROUTE_TABLE_ID])
    assert len(route_table) == 2
    first_route = route_table['RouteTables'][0]['Routes'][0]
    second_route = route_table['RouteTables'][0]['Routes'][1]
    assert first_route['DestinationCidrBlock'] == VPC_CIDR and first_route['GatewayId'] == "local"
    assert second_route['DestinationCidrBlock'] == "0.0.0.0/0" and second_route['NatGatewayId'] == NAT_GATEWAY_ID


def test_public_route_table():
    route_table = CLIENT.describe_route_tables(RouteTableIds=[PUBLIC_ROUTE_TABLE_ID])
    assert len(route_table) == 2
    first_route = route_table['RouteTables'][0]['Routes'][0]
    second_route = route_table['RouteTables'][0]['Routes'][1]
    assert first_route['DestinationCidrBlock'] == VPC_CIDR and first_route['GatewayId'] == "local"
    assert second_route['DestinationCidrBlock'] == "0.0.0.0/0" and second_route['GatewayId'] == INTERNET_GATEWAY_ID


def test_vpc():
    vpc = CLIENT.describe_vpcs(VpcIds=[VPC_ID])
    assert len(vpc['Vpcs']) == 1
    vpc_cidr = vpc['Vpcs'][0]['CidrBlock']
    vpc_instance_tenancy = vpc['Vpcs'][0]['InstanceTenancy']
    assert vpc_cidr == VPC_CIDR
    assert vpc_instance_tenancy == 'default'


def test_subnets():
    private_subnet = CLIENT.describe_subnets(SubnetIds=[PRIVATE_SUBNET_ID])
    public_subnet = CLIENT.describe_subnets(SubnetIds=[PUBLIC_SUBNET_ID])
    protected_subnet = CLIENT.describe_subnets(SubnetIds=[PROTECTED_SUBNET_ID])
    assert len(private_subnet['Subnets']) == 1
    assert len(public_subnet['Subnets']) == 1
    assert len(protected_subnet['Subnets']) == 1
    assert PRIVATE_SUBNET_CIDR == private_subnet['Subnets'][0]['CidrBlock']
    assert PUBLIC_SUBNET_CIDR == public_subnet['Subnets'][0]['CidrBlock']
    assert PROTECTED_SUBNET_CIDR == protected_subnet['Subnets'][0]['CidrBlock']

# Delete the stack at the end of the test.
def exit_handler():
    CF_CLIENT.delete_stack(
    StackName=STACK_NAME
)

atexit.register(exit_handler)
