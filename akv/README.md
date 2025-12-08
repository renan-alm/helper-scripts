*Azure KeyVault CLI tool*

This is a tool to search and fetch secrets from Azure KeyVault. It's built using the msrest azure python SDK and requires a file in your home directory (~/.akv.conf) containing:

```
azure_keyvault_uri: "https://<service name>.vault.azure.net"
```

It also requires certain python libraries that can be found in requirements.txt

```
$pip3 install -r requirements.txt
```

And finally you need to be logged into your azure subscription using the az cli tool:

```
$ az login
```

**Usage**
The tool has two options, search and get.

***Searching for secrets in the keyvault***
Azure KeyVault CLI tool supports multiple keyword searching for secrets. It also supports outputting to both table and json.

``` 
$ akv search sonarqube metrics token
secret_name              secret_type
-----------------------  -------------
sonarqube-metrics-token  token
``` 

***Getting secrets***
```
$ akv get sonarqube-metrics-token
secret                   secret_value
-----------------------  --------------------------------------------
sonarqube-metrics-token  <secret value>
```

***Help***
```
$ akv --help
Usage: akv [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  get
  search
```
