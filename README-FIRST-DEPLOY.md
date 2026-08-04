\# FutureKind First Deployment



Copy



.env.example



to



.env



Create runtime folders



/runtime/postgres



/runtime/redis



/runtime/qdrant



Run



docker compose --profile core up -d



Verify



docker ps



Three containers should be running.



fk-postgres



fk-redis



fk-qdrant

