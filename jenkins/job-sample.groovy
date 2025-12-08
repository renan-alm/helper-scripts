	def schemasToMigrate = ''
	def tasksDeployed = []
	pipeline { 
        agent any

		stages { 
			stage('BUILD') {
                agent {
                    docker {
                        reuseNode true
                        image 'registry.ia.icacorp.net:8443/assortmentstage/assortmentstage-jdk17-2:17-jdk-latest'
                        args '--mount type=bind,source=/data/ab69/.m2/repository,destination=/root/.m2/repository'
                    }
                }

				steps { 
					script {
                        sh '''
                            echo "<settings><servers><server><id>nexus</id><username>$NEXUS_USR</username><password>$NEXUS_PSW</password></server></servers><mirrors><mirror><id>nexus</id><name>Everything</name><mirrorOf>*</mirrorOf><url>https://artifact.ia.icacorp.net/repository/$NEXUS_TEAM</url></mirror></mirrors></settings>" > /root/.m2/settings.xml
                    
                            mvn -f ./db-migration/pom.xml -s mvn-settings.xml clean install
                        '''
	
					}
				}
        }

    
            stage('Build Image') {
                steps {
						 sh 'pwd'
						 sh 'ls'
                    	 sh 'cd db-migration'
                         sh 'docker build .  -t "fra.ocir.io/journeytocloudpaas/assortment-stage-db-migration-ver:version44.0"'
                }
            }

    }		
 }			
