import cv2
import mediapipe as mp
import time
import paho.mqtt.client as mqtt
from paho.mqtt.client import Client
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Configurações MQTT Ubidots
UBIDOTS_TOKEN = "BBUS-BJyEHDkEKc4IqGOh7FzBmEVfwXU5gS"
MQTT_BROKER = "industrial.api.ubidots.com"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "facial-controller"

mqtt_client = Client(client_id=MQTT_CLIENT_ID, protocol=mqtt.MQTTv311)
mqtt_client.username_pw_set(UBIDOTS_TOKEN, password="")
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=True)
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

cap = cv2.VideoCapture(0)

command_mode = False
command_timer_start = 0
command_duration = 8
smile_start_time = 0
smiling = False
eyes_closed = False
eye_close_start_time = 0
action_executed = False
last_action = ""
eyebrow_raised = False
sobrancelha_start_time = 0
em_comando_visivel = False


def calcular_dist_pontos(p1, p2):
    return ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5

def limiar_sobrancelha_dinamico(face_width):
    if face_width <= 96:
        return 31.5
    elif face_width >= 104:
        return 33.5
    else:
        return 31.5 + (face_width - 96) * (33.5 - 31.5) / (104 - 96)

def atualizar_painel(info_list, limiares_list, altura_frame):
    global info_panel
    info_panel = np.zeros((altura_frame, 600, 3), dtype=np.uint8)
    info_panel[:] = (30, 30, 30)
    y = 20

    img_pil = Image.fromarray(cv2.cvtColor(info_panel, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    font_title = ImageFont.truetype("arial.ttf", 20)
    font_info = ImageFont.truetype("arial.ttf", 18)
    font_instr = ImageFont.truetype("arial.ttf", 14)

    draw.text((10, y), ">> MODO COMANDO", font=font_title, fill=(0, 255, 255))
    y += 30
    for texto in info_list:
        draw.text((10, y), texto, font=font_info, fill=(255, 255, 255))
        y += 22

    y_base = altura_frame - 200
    draw.text((10, y_base), ">> INSTRUÇÕES", font=font_title, fill=(255, 255, 0))
    draw.text((310, y_base), ">> LIMIARES", font=font_title, fill=(0, 255, 100))

    y_instr = y_base + 30
    y_limiar = y_base + 30

    instrucoes = [
        "Levantar sobrancelha: Ativar comando",
        "Sorrir 0.5~1.5s: Relé 1 ON",
        "Sorrir 1.5~3s: Relé 2 ON",
        "Sorrir 3~4.5s: Relé 3 ON",
        "Sorrir 4.5~6s: Relé 4 ON",
        "Piscar 0.5~1.5s: Relé 1 OFF",
        "Piscar 1.5~3s: Relé 2 OFF",
        "Piscar 3~4.5s: Relé 3 OFF",
        "Piscar 4.5~6s: Relé 4 OFF"
    ]
    for linha in instrucoes:
        draw.text((10, y_instr), linha, font=font_instr, fill=(180, 255, 180))
        y_instr += 15

    for linha in limiares_list:
        draw.text((310, y_limiar), linha, font=font_info, fill=(200, 200, 200))
        y_limiar += 20

    info_panel = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

def publicar_mqtt(topico, valor):
    mqtt_client.publish(topico, valor)

limiares_list = [
    "Largura ideal: 95–105",
    "Sobrancelha ativar: dinâmico",
    "Sorriso ativar: >70",
    "Olho fechado: <4.0"
]

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(frame_rgb)
    h, w, _ = frame.shape

    info_texts = []
    rosto_detectado = results.multi_face_landmarks is not None

    if not rosto_detectado and em_comando_visivel:
        cv2.rectangle(frame, (0, 0), (w, h), (0, 0, 255), 5)

    if rosto_detectado:
        for face_landmarks in results.multi_face_landmarks:
            mp_drawing.draw_landmarks(
                image=frame,
                landmark_list=face_landmarks,
                connections=mp_face_mesh.FACEMESH_TESSELATION,
                landmark_drawing_spec=mp_drawing.DrawingSpec(color=(0,255,0), thickness=1, circle_radius=1),
                connection_drawing_spec=mp_drawing.DrawingSpec(color=(0,255,0), thickness=1)
            )

            landmarks = face_landmarks.landmark
            eye_outer_left = landmarks[33]
            eye_outer_right = landmarks[263]
            left_point = (int(eye_outer_left.x * w), int(eye_outer_left.y * h))
            right_point = (int(eye_outer_right.x * w), int(eye_outer_right.y * h))
            face_width = calcular_dist_pontos(left_point, right_point)
            info_texts.append(f"Largura do rosto: {face_width:.2f}")

            limiar_sobr = limiar_sobrancelha_dinamico(face_width)
            info_texts.append(f"Limiar sobrancelha (din): {limiar_sobr:.2f}")

            if 95 <= face_width <= 105:
                dentro_range = True
            else:
                dentro_range = False
                msg = "Aproxime-se" if face_width < 95 else "Afaste-se"
                info_texts.append(msg)

            if not dentro_range and not command_mode:
                atualizar_painel(info_texts, limiares_list, h)
                frame_total = np.hstack((frame, info_panel))
                cv2.imshow("Controle Facial", frame_total)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            sobrancelha_top = (int(landmarks[70].x * w), int(landmarks[70].y * h))
            sobrancelha_base = (int(landmarks[159].x * w), int(landmarks[159].y * h))
            sobrancelha_y = calcular_dist_pontos(sobrancelha_top, sobrancelha_base)
            info_texts.append(f"Sobrancelha: {sobrancelha_y:.2f}")

            if sobrancelha_y > limiar_sobr:
                if not eyebrow_raised:
                    sobrancelha_start_time = time.time()
                    eyebrow_raised = True
                elif time.time() - sobrancelha_start_time > 0.5 and not command_mode:
                    command_mode = True
                    command_timer_start = time.time()
                    last_action = ""
                    action_executed = False
                    em_comando_visivel = True
            else:
                eyebrow_raised = False

            if command_mode:
                elapsed = time.time() - command_timer_start
                remaining = max(0, command_duration - int(elapsed))
                info_texts.append(f"Modo de Comando: ATIVO ({remaining}s)")

                smile_width = calcular_dist_pontos(
                    (int(landmarks[61].x * w), int(landmarks[61].y * h)),
                    (int(landmarks[291].x * w), int(landmarks[291].y * h))
                )
                info_texts.append(f"Sorriso: {smile_width:.3f}")

                right_eye_top = (int(landmarks[159].x * w), int(landmarks[159].y * h))
                right_eye_bottom = (int(landmarks[145].x * w), int(landmarks[145].y * h))
                eye_distance = calcular_dist_pontos(right_eye_top, right_eye_bottom)
                info_texts.append(f"Olho Direito: {eye_distance:.3f}")

                if not action_executed:
                    if smile_width > 70:
                        if not smiling:
                            smile_start_time = time.time()
                            smiling = True
                    else:
                        if smiling:
                            duration = time.time() - smile_start_time
                            smiling = False
                            if duration < 0.5:
                                continue
                            if 0.5 <= duration < 1.5:
                                publicar_mqtt("/v1.6/devices/esp32_automation/sala", 1)
                                last_action = "Relé 1 ON via MQTT"
                            elif 1.5 < duration < 3:
                                publicar_mqtt("/v1.6/devices/esp32_automation/cozinha", 1)
                                last_action = "Relé 2 ON via MQTT"
                            elif 3 < duration < 4.5:
                                publicar_mqtt("/v1.6/devices/esp32_automation/quarto", 1)
                                last_action = "Relé 3 ON via MQTT"
                            elif 4.5 < duration < 6:
                                publicar_mqtt("/v1.6/devices/esp32_automation/banheiro", 1)
                                last_action = "Relé 4 ON via MQTT"
                            action_executed = True

                    if smiling:
                        duration = time.time() - smile_start_time
                        info_texts.append(f"Tempo de Sorriso: {duration:.1f}s")

                    if eye_distance < 4.0:
                        if not eyes_closed:
                            eye_close_start_time = time.time()
                            eyes_closed = True
                    else:
                        if eyes_closed:
                            duration = time.time() - eye_close_start_time
                            eyes_closed = False
                            if duration < 0.5:
                                continue
                            if 0.5 <= duration < 1.5:
                                publicar_mqtt("/v1.6/devices/esp32_automation/sala", 0)
                                last_action = "Relé 1 OFF via MQTT"
                            elif 1.5 < duration < 3:
                                publicar_mqtt("/v1.6/devices/esp32_automation/cozinha", 0)
                                last_action = "Relé 2 OFF via MQTT"
                            elif 3 < duration < 4.5:
                                publicar_mqtt("/v1.6/devices/esp32_automation/quarto", 0)
                                last_action = "Relé 3 OFF via MQTT"
                            elif 4.5 < duration < 6:
                                publicar_mqtt("/v1.6/devices/esp32_automation/banheiro", 0)
                                last_action = "Relé 4 OFF via MQTT"
                            action_executed = True

                    if eyes_closed:
                        duration = time.time() - eye_close_start_time
                        info_texts.append(f"Tempo Olho Fechado: {duration:.1f}s")

                if elapsed > command_duration:
                    command_mode = False
                    smiling = False
                    eyes_closed = False
                    action_executed = False
                    em_comando_visivel = False

            if last_action:
                info_texts.append(f"Ação: {last_action}")

    if rosto_detectado or em_comando_visivel:
        atualizar_painel(info_texts, limiares_list, h)
        frame_total = np.hstack((frame, info_panel))
        cv2.imshow("Controle Facial", frame_total)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
