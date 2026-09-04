{{- define "vllm.labels" -}}
app.kubernetes.io/name: vllm
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: steakllm
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
steakllm.io/service: vllm
{{- end }}

{{- define "vllm.selectorLabels" -}}
app.kubernetes.io/name: vllm
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
