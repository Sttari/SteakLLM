{{- define "gateway.labels" -}}
app.kubernetes.io/name: gateway
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: steakllm
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
steakllm.io/service: gateway
{{- end }}

{{- define "gateway.selectorLabels" -}}
app.kubernetes.io/name: gateway
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
