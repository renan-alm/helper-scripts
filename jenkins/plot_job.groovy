def used

pipeline{
    agent {
      label &apos;slim&apos;
    }
    environment{
        GITHUB=credentials(&quot;github-user&quot;)
    }
    stages{
        stage(&apos;GH API&apos;){
            steps{
                script{
                    def user = &quot;${env.GITHUB_USR}&quot;
                    def password = &quot;${env.GITHUB_PSW}&quot;
                    def gitHubAPI = new URL(&quot;https://api.github.com/rate_limit&quot;)
                    def authHeader = &quot;Basic &quot; + &quot;${user}:${password}&quot;.bytes.encodeBase64().toString()
                    HttpURLConnection conn = (HttpURLConnection) gitHubAPI.openConnection()
                    conn.addRequestProperty(&quot;Accept&quot;, &quot;application/json&quot;)
                    conn.setRequestProperty(&quot;Authorization&quot;, authHeader)
                    conn.with {
                        println &quot;response code: ${conn.responseCode}&quot;
                        def body = new groovy.json.JsonSlurper().parseText(conn.getInputStream().text)
                        used = body.rate.used
                        println &quot;Number ${body.rate.used}&quot;
                        }
                    conn = null
                }
                writeCSV(file:&apos;output.csv&apos;, records:[[&apos;used_quota&apos;],[used]], format:CSVFormat.EXCEL)
                sh &quot;cat output.csv&quot;
                plot csvFileName: &apos;plot-a4495877-82a3-4a1c-9d1e-47e81f3f943c.csv&apos;, csvSeries: [[displayTableFlag: false, exclusionValues: &apos;&apos;, file: &apos;output.csv&apos;, inclusionFlag: &apos;OFF&apos;, url: &apos;&apos;]], description: &apos;Description&apos;, group: &apos;group&apos;, numBuilds: &apos;200&apos;, style: &apos;line&apos;, title: &apos;Title&apos;, useDescr: true, yaxis: &apos;Y-label&apos;, yaxisMaximum: &apos;7000&apos;, yaxisMinimum: &apos;0&apos;
            }
        }
    }
}