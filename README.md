# Cloudformation stack template generator using Trophosphere
![GithubCI](https://github.com/mohammedx3/template-generator/actions/workflows/build-template-generator.yaml/badge.svg
)

A Trophosphere application based on Python3 to create multiple AWS Cloudformation stacks each will include a VPC and 3 subnets with equal number of hosts, one is completely private without any access to the internet, one is public with open access to the internet and a protected one which can access the internet via a NAT gateway.

## Usage
- Install requirements.
    ```sh
    pip3 install -r requirements.txt
    ```
- Run the template generator.
    ```sh
    python3 template_generator.py
    ```

## Flags
```sh
--input_path 
--output_path 
```
Flags are optional, if needed you can specify the path from which data about the environment will be fetched. (defaults to the working dir and looks for `values.yaml`). And the path to where to save the generated template.

## Values.yaml
Contains needed data about the environment in order to create vpc, subnets, etc..
```yaml
dev:
  region: us-east-1
  availabilityZones:
  - us-east-1a
  - us-east-1b
  - us-east-1c
  vpcIp: 10.0.0.0
  netMask: 24
  dnsSupport: true
  dnsHostnames: false
  instanceTenancy: default
```
NOTE: 
- You can tweak these data as needed but be careful to use a valid cidr with the correct mask so the template generator is able to split it into 3 subnets, you can also add more environments if needed.
- Each environment will have its own template file. (ex: if you add 3 environments you will get 3 template files each with the environments' names)

### IPSplitter
`IPSplitter` class is used to split the network into equal subnets.
```py
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
```

### Template creation
Template is mainly consisted of `Parameters`, `Resources` and `Output`.
I'm creating the template using Trophosphere library.
```py
VPCCIDR = t.add_parameter(
    Parameter(
        "VPCCIDR",
        Description="IP Address range for the VPC",
        Default="10.0.0.0/24",
    )
)
```

## Test
- In testing we are basically trying to create the stack, wait until the stack is in a `CREATE_COMPLETE` state then use `boto3` library to describe each of the created resources' IDs to run some checks to make sure that the stack was built successfully and it has the correct resources and values.
```py
CF_CLIENT.create_stack(StackName=STACK_NAME, TemplateBody=TEMPLATE_CONTENT)
WAITER = CF_CLIENT.get_waiter('stack_create_complete').wait(StackName=STACK_NAME)
```
```py
state = internet_gateway['InternetGateways'][0]['Attachments'][0]['State']
assert state == 'available'
```

- Whether the test passed or failed, the stack will get deleted after the test is complete using `atexit`.
```py
def exit_handler():
    CF_CLIENT.delete_stack(
    StackName=STACK_NAME
)
atexit.register(exit_handler)
```
PyTest is used to run the tests:
```sh
collecting ... Creating test-template-generator
Waiting for stack creation to complete...
collected 6 items                                                                                                                                                                

test_template.py::test_nat_gateway PASSED
test_template.py::test_internet_gateway PASSED
test_template.py::test_protected_route_table PASSED
test_template.py::test_public_route_table PASSED
test_template.py::test_vpc PASSED
test_template.py::test_subnets PASSED

========================================================================= 6 passed in 192.18s (0:03:12) ==========================================================================
```

## Docker
Template generator is available as a docker image, just build and run it. (Output is the generated template)
```sh
docker build . -t templategenerator
docker run -it templategenerator
```

## CI
A github workflow is used to run:
- `flake8` for linting.
- Run the template generator with visible output.
- Run pytest to create the stack in AWS and do the needed checks.
