#include <WiFi.h>
#include <PubSubClient.h>
#include "DHT.h"

#define DHTPIN 4
#define DHTTYPE DHT22

DHT dht(DHTPIN, DHTTYPE);

// Credenciais Wi-Fi
const char* ssid = "SEU_WIFI";
const char* password = "SENHA_WIFI";

// Ubidots MQTT
const char* mqtt_server = "industrial.api.ubidots.com";
const char* mqtt_token = "SEU_TOKEN_AQUI";  
const char* device_label = "seu_device_label"; 

WiFiClient espClient;
PubSubClient client(espClient);

// Pinos dos relés
const int releSala = 16;
const int releQuarto = 17;
const int releCozinha = 18;
const int releBanheiro = 19;

TaskHandle_t TaskSensor;
TaskHandle_t TaskMQTT;

void conectarWiFi() {
  WiFi.begin(ssid, password);
  Serial.print("Conectando no Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(" conectado!");
}

void callback(char* topic, byte* payload, unsigned int length) {
  String topico = String(topic);
  String valorStr = "";

  for (unsigned int i = 0; i < length; i++) {
    valorStr += (char)payload[i];
  }

  int valor = valorStr.toInt();
  bool estado = valor == 1;

  if (topico.endsWith("/sala/lv")) digitalWrite(releSala, estado);
  if (topico.endsWith("/quarto/lv")) digitalWrite(releQuarto, estado);
  if (topico.endsWith("/cozinha/lv")) digitalWrite(releCozinha, estado);
  if (topico.endsWith("/banheiro/lv")) digitalWrite(releBanheiro, estado);
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Conectando ao MQTT...");
    if (client.connect("ESP32Client", mqtt_token, "")) {
      Serial.println("conectado");
      client.subscribe("/v1.6/devices/seu_device_label/sala/lv");
      client.subscribe("/v1.6/devices/seu_device_label/quarto/lv");
      client.subscribe("/v1.6/devices/seu_device_label/cozinha/lv");
      client.subscribe("/v1.6/devices/seu_device_label/banheiro/lv");
    } else {
      Serial.print("Falha, rc=");
      Serial.print(client.state());
      delay(2000);
    }
  }
}

void loopSensor(void* parameter) {
  for (;;) {
    float temperatura = dht.readTemperature();
    float umidade = dht.readHumidity();

    if (!isnan(temperatura) && !isnan(umidade)) {
      char tempStr[10], umiStr[10];
      dtostrf(temperatura, 4, 1, tempStr);
      dtostrf(umidade, 4, 1, umiStr);

      client.publish("/v1.6/devices/seu_device_label/temperatura", tempStr);
      client.publish("/v1.6/devices/seu_device_label/umidade", umiStr);
    }

    vTaskDelay(5000 / portTICK_PERIOD_MS);
  }
}

void loopMQTT(void* parameter) {
  for (;;) {
    if (!client.connected()) {
      reconnect();
    }
    client.loop();

    client.publish("/v1.6/devices/seu_device_label/sala_status", digitalRead(releSala) ? "1" : "0");
    client.publish("/v1.6/devices/seu_device_label/quarto_status", digitalRead(releQuarto) ? "1" : "0");
    client.publish("/v1.6/devices/seu_device_label/cozinha_status", digitalRead(releCozinha) ? "1" : "0");
    client.publish("/v1.6/devices/seu_device_label/banheiro_status", digitalRead(releBanheiro) ? "1" : "0");

    vTaskDelay(5000 / portTICK_PERIOD_MS);
  }
}

void setup() {
  Serial.begin(115200);
  dht.begin();

  pinMode(releSala, OUTPUT);
  pinMode(releQuarto, OUTPUT);
  pinMode(releCozinha, OUTPUT);
  pinMode(releBanheiro, OUTPUT);

  conectarWiFi();
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);

  xTaskCreatePinnedToCore(loopSensor, "TaskSensor", 4000, NULL, 1, &TaskSensor, 1);
  xTaskCreatePinnedToCore(loopMQTT, "TaskMQTT", 4000, NULL, 1, &TaskMQTT, 1);
}

void loop() {
  // Não utilizado, FreeRTOS cuida das tasks
}
